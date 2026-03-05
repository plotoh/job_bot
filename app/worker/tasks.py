# app/worker/tasks.py
import asyncio
import logging
import random
from datetime import date, datetime
from typing import Optional

import aiohttp
import pytz
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.database.models import Account, Vacancy, AccountVacancy, Response
from app.services.hh_api import HHApiClient
from app.services.vacancy_filter import is_backend_python_keywords, extract_secret_word
from app.services.vacancy_parser import HHSearcher, HHDetailParser
from app.services.letter_generator import generate_cover_letter
from app.services.response_sender import send_response, ensure_cookies
from app.services.login import login_and_get_cookies
from app.utils.proxy_rotator import get_proxy_for_account
from app.utils.encryption import decrypt_password
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def get_db_session():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_async_engine(
            f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
            echo=False
        )
        _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)
    return _SessionLocal


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


# ---------- Парсинг всех новых вакансий ----------
@celery_app.task
def parse_all_vacancies():
    logger.info("Starting parse_all_vacancies task")
    run_async(_parse_all_vacancies())


async def _parse_all_vacancies():
    async with get_db_session()() as session:
        accounts = await session.execute(select(Account).where(Account.is_active == True))
        accounts = accounts.scalars().all()
        logger.info(f"Found {len(accounts)} active accounts")

        all_vacancies = []
        for account in accounts:
            search_filter = account.search_filter or {}
            if not search_filter.get("url"):
                logger.debug(f"Account {account.id} has no search filter, skipping")
                continue

            # Получаем cookies (если нет, пробуем обновить)
            cookies = account.cookies or {}
            if not cookies:
                try:
                    cookies = await login_and_get_cookies(
                        account.username,
                        decrypt_password(account.password_encrypted)
                    )
                    account.cookies = cookies
                    await session.commit()
                except Exception as e:
                    logger.error(f"Failed to login for account {account.id}: {e}")
                    continue

            searcher = HHSearcher(
                account_id=account.id,
                cookies=cookies,
                resume_hash=account.resume_id,
                proxy=get_proxy_for_account(account.id)
            )
            try:
                vacancies = await searcher.search(
                    search_url=search_filter["url"],
                    max_pages=account.max_pages)
                logger.info(f"Account {account.id}: found {len(vacancies)} vacancies on search pages")
                all_vacancies.extend(vacancies)
            except Exception as e:
                logger.error(f"Error searching vacancies for account {account.id}: {e}", exc_info=True)
                continue

        # Убираем дубликаты по hh_id
        unique_vacs = {v["id"]: v for v in all_vacancies if v.get("id")}.values()
        logger.info(f"Total unique vacancies found: {len(unique_vacs)}")

        for vac_data in unique_vacs:
            existing = await session.execute(
                select(Vacancy).where(Vacancy.hh_id == str(vac_data["id"]))
            )
            if existing.scalar_one_or_none():
                continue

            # Получаем детали вакансии (используем cookies любого аккаунта или создаём временный клиент)
            # Для простоты используем cookies первого попавшегося аккаунта
            parser = HHDetailParser(cookies=cookies, proxy=get_proxy_for_account(0))
            details = await parser.parse(vac_data["id"])
            if "error" in details:
                logger.error(f"Error parsing details for vacancy {vac_data['id']}: {details['error']}")
                continue

            # Фильтрация по ключевым словам
            if not is_backend_python_keywords(vac_data["title"], details.get("description", "")):
                logger.info(f"Vacancy {vac_data['title']} does not match backend Python keywords, skipping")
                continue

            # Извлечение проверочного слова
            secret = extract_secret_word(details.get("description", ""))

            new_vac = Vacancy(
                hh_id=str(vac_data["id"]),
                title=vac_data["title"],
                url=vac_data["link"],
                description=details.get("description", ""),
                check_word=secret
            )
            session.add(new_vac)
            await session.commit()
            logger.info(f"Saved new vacancy: {vac_data['title']} (ID: {vac_data['id']})")


# ---------- Генерация и отправка откликов ----------
@celery_app.task
def generate_and_send_responses():
    logger.info("Starting generate_and_send_responses task")
    run_async(_generate_and_send_responses())


def is_working_hours(account: Account) -> bool:
    msk_tz = pytz.timezone('Europe/Moscow')
    now_msk = datetime.now(msk_tz)
    hour = now_msk.hour
    return account.work_start_hour <= hour < account.work_end_hour


async def _generate_and_send_responses():
    async with get_db_session()() as session:
        accounts = await session.execute(select(Account).where(Account.is_active == True))
        accounts = accounts.scalars().all()
        logger.info(f"Processing responses for {len(accounts)} accounts")

        for account in accounts:
            if not is_working_hours(account):
                logger.debug(f"Account {account.id} is outside working hours, skipping")
                continue

            # Сброс лимита, если новый день
            await _reset_daily_limit_if_needed(account, session)

            remaining = account.daily_response_limit - account.responses_today
            if remaining <= 0:
                logger.info(
                    f"Account {account.id} has reached daily limit ({account.responses_today}/{account.daily_response_limit})")
                continue

            # Выбираем вакансии, на которые ещё нет связи
            subq = select(AccountVacancy.vacancy_id).where(AccountVacancy.account_id == account.id)
            stmt = select(Vacancy).where(Vacancy.id.not_in(subq)).order_by(func.random()).limit(remaining)
            vacancies = await session.execute(stmt)
            vacancies = vacancies.scalars().all()
            logger.info(f"Account {account.id}: found {len(vacancies)} new vacancies to respond")

            if not vacancies:
                continue

            auth_failed = False
            for vacancy in vacancies:
                if auth_failed:
                    break

                account_vacancy = AccountVacancy(
                    account_id=account.id,
                    vacancy_id=vacancy.id,
                    viewed_at=datetime.utcnow(),
                    responded=False
                )
                session.add(account_vacancy)
                await session.commit()

                try:
                    letter = await generate_cover_letter(
                        vacancy_title=vacancy.title,
                        vacancy_description=vacancy.description,
                        company="",  # не используется
                        resume_text=account.resume_text,
                        secret_word=vacancy.check_word,
                        tg_username=account.telegram_username
                    )
                    logger.info(f"Generated letter for vacancy {vacancy.id} (length: {len(letter)})")
                except Exception as e:
                    logger.error(f"Failed to generate letter for vacancy {vacancy.id}: {e}", exc_info=True)
                    await session.delete(account_vacancy)
                    await session.commit()
                    continue

                response = Response(
                    account_id=account.id,
                    vacancy_id=vacancy.id,
                    cover_letter=letter,
                    status="pending"
                )
                session.add(response)
                await session.commit()
                await session.refresh(response)

                account_vacancy.responded = True
                account_vacancy.response_id = response.id
                await session.commit()

                account.responses_today += 1
                await session.commit()

                try:
                    success = await send_response(account.id, vacancy.id, response.id)
                    if success:
                        response.status = "sent"
                        response.sent_at = datetime.utcnow()
                        logger.info(f"Response {response.id} sent successfully for account {account.id}")
                    else:
                        response.status = "error"
                        response.error_message = "send_response returned False"
                        logger.error(f"send_response returned False for response {response.id}")
                except Exception as e:
                    logger.error(f"Exception while sending response {response.id}: {e}", exc_info=True)
                    response.status = "error"
                    response.error_message = str(e)
                    await send_telegram_message(
                        account.id,
                        f"⚠️ Ошибка при отправке отклика на вакансию «{vacancy.title}».\n"
                        f"Причина: {str(e)[:200]}\n"
                        f"Проверьте настройки аккаунта (логин/пароль) и повторите попытку."
                    )
                    auth_failed = True
                finally:
                    await session.commit()

                if not auth_failed and account.responses_today < account.daily_response_limit:
                    delay = random.randint(account.response_interval_min, account.response_interval_max)
                    logger.info(f"Account {account.id}: waiting {delay} seconds before next response")
                    await asyncio.sleep(delay)

            logger.info(f"Account {account.id}: sent {account.responses_today} responses today.")


async def _reset_daily_limit_if_needed(account: Account, session):
    today = date.today()
    if account.last_reset_date < today:
        account.responses_today = 0
        account.daily_response_limit = random.randint(account.daily_limit_min, account.daily_limit_max)
        account.last_reset_date = today
        await session.commit()
        logger.info(f"Account {account.id} daily limit reset to {account.daily_response_limit}")


# ---------- Сброс лимитов ----------
@celery_app.task
def reset_daily_limits():
    logger.info("Starting reset_daily_limits task")
    run_async(_reset_daily_limits())


async def _reset_daily_limits():
    async with get_db_session()() as session:
        await session.execute(
            update(Account).values(responses_today=0, last_reset_date=date.today())
        )
        await session.commit()
    logger.info("Daily limits reset for all accounts.")


# ---------- Тестовый запуск ----------
@celery_app.task
def run_test_for_account(account_id: int, chat_id: int):
    logger.info(f"Starting test for account {account_id}, chat {chat_id}")
    run_async(_run_test_for_account(account_id, chat_id))


async def _run_test_for_account(account_id: int, chat_id: int):
    async with get_db_session()() as session:
        account = await session.get(Account, account_id)
        if not account:
            await send_telegram_message(chat_id, "❌ Аккаунт не найден.")
            logger.error(f"Account {account_id} not found for test")
            return

        # Выбираем случайные вакансии, на которые нет связи
        subq = select(AccountVacancy.vacancy_id).where(AccountVacancy.account_id == account_id)
        stmt = select(Vacancy).where(Vacancy.id.not_in(subq)).order_by(func.random()).limit(account.test_count)
        vacancies = await session.execute(stmt)
        vacancies = vacancies.scalars().all()

        if not vacancies:
            await send_telegram_message(chat_id, "❌ Нет новых вакансий для теста.")
            logger.warning(f"No new vacancies for account {account_id} test")
            return

        report = [f"<b>Тестовый запуск для аккаунта {account.username}</b>"]
        report.append(f"Настройки: парсинг={'✅' if account.test_parse_vacancy else '❌'}, "
                      f"генерация={'✅' if account.test_generate_letter else '❌'}, "
                      f"отправка={'✅' if account.test_send_response else '❌'}")
        report.append(f"Количество тестов: {len(vacancies)}\n")

        for i, vacancy in enumerate(vacancies, 1):
            try:
                letter = await generate_cover_letter(
                    vacancy_title=vacancy.title,
                    vacancy_description=vacancy.description,
                    company="",
                    resume_text=account.resume_text,
                    secret_word=vacancy.check_word,
                    tg_username=account.telegram_username
                )
                if not letter or len(letter.strip()) < 10:
                    raise ValueError("Сгенерированное письмо слишком короткое или пустое")

                report.append(f"<b>Тест {i}: {vacancy.title}</b>")
                report.append(f"🔗 {vacancy.url}")
                report.append(f"📝 <b>Письмо:</b>\n{letter}\n")
                logger.info(f"Test for account {account_id}, vacancy {vacancy.id}: letter generated successfully")
            except Exception as e:
                error_msg = f"❌ Ошибка при генерации письма для {vacancy.title}: {e}"
                report.append(error_msg)
                logger.error(f"Test error for account {account_id}, vacancy {vacancy.id}: {e}", exc_info=True)

        full_text = "\n".join(report)
        if len(full_text) > 4000:
            for i in range(0, len(full_text), 4000):
                await send_telegram_message(chat_id, full_text[i:i + 4000])
        else:
            await send_telegram_message(chat_id, full_text)


# ---------- Парсинг для конкретного аккаунта ----------
@celery_app.task
def parse_new_vacancies_for_account(account_id: int):
    logger.info(f"Starting parse_new_vacancies_for_account for account {account_id}")
    run_async(_parse_new_vacancies_for_account(account_id))


async def _parse_new_vacancies_for_account(account_id: int):
    async with get_db_session()() as session:
        account = await session.get(Account, account_id)
        if not account or not account.is_active:
            logger.warning(f"Account {account_id} not found or inactive")
            return

        search_filter = account.search_filter or {}
        if not search_filter.get("url"):
            logger.warning(f"Account {account_id} has no search filter")
            return

        cookies = account.cookies or {}
        if not cookies:
            try:
                username, password = account.username, decrypt_password(account.password_encrypted)
                cookies = await login_and_get_cookies(username, password)
                account.cookies = cookies
                await session.commit()
            except Exception as e:
                logger.error(f"Failed to login for account {account_id} with username: {username}, password: {password} and cookies: {cookies} error: {e}")
                logger.error(f"Failed to login for account {account_id}: {e}")
                return

        searcher = HHSearcher(
            account_id=account_id,
            cookies=cookies,
            resume_hash=account.resume_id,
            proxy=get_proxy_for_account(account_id)
        )
        try:
            vacancies = await searcher.search(
                search_url=search_filter["url"],
                max_pages=account.max_pages
            )
            logger.info(f"Account {account_id}: found {len(vacancies)} vacancies on search pages")
        except Exception as e:
            logger.error(f"Error searching vacancies for account {account_id}: {e}", exc_info=True)
            return

        for vac_data in vacancies:
            if not vac_data.get("id"):
                continue

            existing_vac = await session.execute(
                select(Vacancy).where(Vacancy.hh_id == str(vac_data["id"]))
            )
            vacancy = existing_vac.scalar_one_or_none()

            if not vacancy:
                parser = HHDetailParser(cookies=cookies, proxy=get_proxy_for_account(0))
                details = await parser.parse(vac_data["id"])
                if "error" in details:
                    logger.error(f"Error parsing details for vacancy {vac_data['id']}: {details['error']}")
                    continue

                if not is_backend_python_keywords(vac_data["title"], details.get("description", "")):
                    logger.info(f"Vacancy {vac_data['title']} does not match backend Python, skipping")
                    continue

                new_vac = Vacancy(
                    hh_id=str(vac_data["id"]),
                    title=vac_data["title"],
                    url=vac_data["link"],
                    description=details.get("description", ""),
                    check_word=extract_secret_word(details.get("description", ""))
                )
                session.add(new_vac)
                await session.commit()
                vacancy = new_vac
                logger.info(f"Saved new vacancy {vac_data['id']} for account {account_id}")

            # Проверяем, есть ли связь с аккаунтом
            av_exists = await session.execute(
                select(AccountVacancy).where(
                    AccountVacancy.account_id == account.id,
                    AccountVacancy.vacancy_id == vacancy.id
                )
            )
            if not av_exists.scalar_one_or_none():
                account_vacancy = AccountVacancy(
                    account_id=account.id,
                    vacancy_id=vacancy.id,
                    viewed_at=datetime.utcnow(),
                    responded=False
                )
                session.add(account_vacancy)
                await session.commit()
                logger.info(f"Created account_vacancy link for account {account_id}, vacancy {vacancy.id}")


# ---------- Обновление cookies ----------
@celery_app.task
def refresh_all_cookies():
    logger.info("Starting refresh_all_cookies task")
    run_async(_refresh_all_cookies())


async def _refresh_all_cookies():
    async with get_db_session()() as session:
        accounts = await session.execute(select(Account))
        accounts = accounts.scalars().all()
        for account in accounts:
            # Проверяем, если cookies отсутствуют или старше 12 часов
            need_refresh = False
            if not account.cookies:
                need_refresh = True
            elif hasattr(account, 'cookies_updated_at') and account.cookies_updated_at:
                age = datetime.utcnow() - account.cookies_updated_at
                if age.total_seconds() > 12 * 3600:
                    need_refresh = True
            else:
                # Если нет поля updated_at, пробуем проверить через is_logged_in
                client = HHApiClient(
                    account.id,
                    account.cookies,
                    account.resume_id,
                    proxy=get_proxy_for_account(account.id)
                )
                if not client.is_logged_in():
                    need_refresh = True

            if need_refresh:
                try:
                    logger.info(f"Refreshing cookies for account {account.id}")
                    new_cookies = await login_and_get_cookies(
                        account.username,
                        decrypt_password(account.password_encrypted)
                    )
                    account.cookies = new_cookies
                    if hasattr(account, 'cookies_updated_at'):
                        account.cookies_updated_at = datetime.utcnow()
                    await session.commit()
                except Exception as e:
                    logger.error(f"Failed to refresh cookies for account {account.id}: {e}")
