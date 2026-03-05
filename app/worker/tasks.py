# app/worker/tasks.py
import asyncio
import logging
import random
from datetime import date, datetime
from typing import List, Dict, Optional

import aiohttp
import pytz
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.models import Account, Vacancy, AccountVacancy, Response, Base
from app.services.vacancy_filter import is_backend_python_keywords, extract_secret_word
from app.utils.proxy_rotator import get_proxy_for_account
from app.worker.celery_app import celery_app
from app.services.response_sender import send_response
from app.services.letter_generator import generate_cover_letter
from app.services.hh_parser import HHParser

logger = logging.getLogger(__name__)

# Ленивое создание асинхронного движка и сессии
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
    """Вспомогательная функция для запуска асинхронной корутины в синхронной Celery-задаче."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ---------- Парсинг всех новых вакансий (общий) ----------
@celery_app.task
def parse_all_vacancies():
    """Собирает вакансии по фильтрам всех активных аккаунтов и сохраняет в общую таблицу vacancies."""
    run_async(_parse_all_vacancies())


async def _parse_all_vacancies():
    async with get_db_session()() as session:
        result = await session.execute(select(Account).where(Account.is_active == True))
        accounts = result.scalars().all()

        all_vacancies = []
        for account in accounts:
            search_filter = account.search_filter
            if not search_filter.get("url"):
                continue

            proxy = get_proxy_for_account(account.id)
            parser = HHParser(account_id=account.id, proxy=proxy)

            try:
                vacancies = await parser.search_vacancies(
                    search_url=search_filter["url"],
                    max_pages=search_filter.get("max_pages", 1)
                )
                all_vacancies.extend(vacancies)
            except Exception as e:
                logger.error(f"Error parsing vacancies for account {account.id}: {e}")
                continue

        unique_vacs = {v["id"]: v for v in all_vacancies if v.get("id")}.values()

        for vac_data in unique_vacs:
            existing = await session.execute(
                select(Vacancy).where(Vacancy.hh_id == vac_data["id"])
            )
            if existing.scalar_one_or_none():
                continue

            proxy = get_proxy_for_account(0)
            parser = HHParser(account_id=0, proxy=proxy)
            try:
                details = await parser.parse_vacancy_details(vac_data["link"])
                if "error" in details:
                    logger.error(f"Error parsing details for {vac_data['link']}: {details['error']}")
                    continue
            except Exception as e:
                logger.error(f"Exception parsing details for {vac_data['link']}: {e}")
                continue

            if not is_backend_python_keywords(vac_data["title"], details.get("description", "")):
                logger.info(f"Vacancy {vac_data['title']} does not match backend Python, skipping")
                continue

            description = details.get("description", "")
            secret = extract_secret_word(description)
            if not secret and description:
                secret = await _extract_secret_word_llm(description)

            new_vac = Vacancy(
                hh_id=vac_data["id"],
                title=vac_data["title"],
                url=vac_data["link"],
                description=description,
                check_word=secret
            )
            session.add(new_vac)
            await session.commit()
            logger.info(f"Saved new vacancy: {vac_data['title']} (ID: {vac_data['id']})")


async def _extract_secret_word_llm(description: str) -> Optional[str]:
    import ollama
    prompt = f"Найди в тексте вакансии проверочное слово, которое кандидат должен указать в отклике. Если такого слова нет, ответь 'НЕТ'. Текст:\n\n{description[:2000]}"
    try:
        response = ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0}
        )
        answer = response["message"]["content"].strip()
        if answer.upper() == "НЕТ" or len(answer) > 50:
            return None
        return answer
    except Exception as e:
        logger.error(f"LLM secret word extraction failed: {e}")
        return None


# ---------- Генерация и отправка откликов для всех аккаунтов ----------
@celery_app.task
def generate_and_send_responses():
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

        for account in accounts:
            if not is_working_hours(account):
                continue
            await _reset_daily_limit_if_needed(account, session)

            remaining = account.daily_response_limit - account.responses_today
            if remaining <= 0:
                continue

            # Выбираем вакансии, на которые ещё нет связи AccountVacancy (не просмотрены)
            subq = select(AccountVacancy.vacancy_id).where(AccountVacancy.account_id == account.id)
            stmt = select(Vacancy).where(Vacancy.id.not_in(subq)).order_by(func.random()).limit(remaining)
            vacancies = await session.execute(stmt)
            vacancies = vacancies.scalars().all()
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
                        company="Компания",
                        resume_text=account.resume_text,
                        secret_word=vacancy.check_word,
                        system_prompt=account.system_prompt,
                        tg_username=account.telegram_username
                    )
                except Exception as e:
                    logger.error(f"Failed to generate letter for vacancy {vacancy.id}: {e}")
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
                        logger.info(f"Response {response.id} sent for account {account.id}")
                    else:
                        response.status = "error"
                        response.error_message = "send_response returned False"
                except Exception as e:
                    logger.error(f"Failed to send response {response.id}: {e}")
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

            logger.info(f"Account {account.id}: generated {account.responses_today} responses today.")


async def _reset_daily_limit_if_needed(account: Account, session: AsyncSession):
    today = date.today()
    if account.last_reset_date < today:
        account.responses_today = 0
        account.daily_response_limit = random.randint(account.daily_limit_min, account.daily_limit_max)
        account.last_reset_date = today
        await session.commit()
        logger.info(f"Account {account.id} new daily limit: {account.daily_response_limit}")


# ---------- Отдельная задача для сброса лимитов ----------
@celery_app.task
def reset_daily_limits():
    run_async(_reset_daily_limits())


async def _reset_daily_limits():
    async with get_db_session()() as session:
        await session.execute(
            update(Account).values(responses_today=0, last_reset_date=date.today())
        )
        await session.commit()
    logger.info("Daily limits reset for all accounts.")


# ---------- Вспомогательная функция для отправки сообщений в Telegram ----------
async def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


# ---------- Тестовый запуск для аккаунта ----------
@celery_app.task
def run_test_for_account(account_id: int, chat_id: int):
    run_async(_run_test_for_account(account_id, chat_id))


async def _run_test_for_account(account_id: int, chat_id: int):
    async with get_db_session()() as session:
        account = await session.get(Account, account_id)
        if not account:
            await send_telegram_message(chat_id, "❌ Аккаунт не найден.")
            return

        # Выбираем случайные вакансии, на которые у аккаунта ещё нет связи (не просмотрены)
        subq = select(AccountVacancy.vacancy_id).where(AccountVacancy.account_id == account_id)
        stmt = select(Vacancy).where(Vacancy.id.not_in(subq)).order_by(func.random()).limit(account.test_count)
        vacancies = await session.execute(stmt)
        vacancies = vacancies.scalars().all()

        if not vacancies:
            await send_telegram_message(chat_id, "❌ Нет новых вакансий для теста.")
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
                    company="Компания",
                    resume_text=account.resume_text,
                    secret_word=vacancy.check_word,
                    system_prompt=account.system_prompt,
                    tg_username=account.telegram_username
                )
                report.append(f"<b>Тест {i}: {vacancy.title}</b>")
                report.append(f"🔗 {vacancy.url}")
                report.append(f"📝 <b>Письмо:</b>\n{letter}\n")
            except Exception as e:
                report.append(f"❌ Ошибка при генерации письма для {vacancy.title}: {e}")

        full_text = "\n".join(report)
        if len(full_text) > 4000:
            for i in range(0, len(full_text), 4000):
                await send_telegram_message(chat_id, full_text[i:i+4000])
        else:
            await send_telegram_message(chat_id, full_text)


# ---------- Парсинг новых вакансий для конкретного аккаунта ----------
@celery_app.task
def parse_new_vacancies_for_account(account_id: int):
    run_async(_parse_new_vacancies_for_account(account_id))


async def _parse_new_vacancies_for_account(account_id: int):
    async with get_db_session()() as session:
        account = await session.get(Account, account_id)
        if not account or not account.is_active:
            return

        search_filter = account.search_filter
        if not search_filter.get("url"):
            logger.warning(f"Account {account_id} has no search filter")
            return

        proxy = get_proxy_for_account(account_id)
        parser = HHParser(account_id=account_id, proxy=proxy)

        try:
            vacancies = await parser.search_vacancies(
                search_url=search_filter["url"],
                max_pages=search_filter.get("max_pages", 1)
            )
        except Exception as e:
            logger.error(f"Error parsing vacancies for account {account_id}: {e}")
            return

        for vac_data in vacancies:
            if not vac_data.get("id"):
                continue

            existing_vac = await session.execute(
                select(Vacancy).where(Vacancy.hh_id == vac_data["id"])
            )
            vacancy = existing_vac.scalar_one_or_none()

            if not vacancy:
                try:
                    details = await parser.parse_vacancy_details(vac_data["link"])
                    if "error" in details:
                        logger.error(f"Error parsing details for {vac_data['link']}: {details['error']}")
                        continue
                except Exception as e:
                    logger.error(f"Error parsing details for {vac_data['link']}: {e}")
                    continue

                if not is_backend_python_keywords(vac_data["title"], details.get("description", "")):
                    continue

                new_vac = Vacancy(
                    hh_id=vac_data["id"],
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