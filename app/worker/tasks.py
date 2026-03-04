# app/worker/tasks.py
import asyncio
import logging
import random
from datetime import date, datetime
from typing import List, Dict, Optional

import aiohttp
import pytz
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import AsyncSessionLocal, Account, Vacancy, AccountVacancy, Response
from app.services.vacancy_filter import is_backend_python_keywords, extract_secret_word
from app.utils.proxy_rotator import get_proxy_for_account
from app.worker.celery_app import celery_app
from app.services.response_sender import send_response
from app.services.letter_generator import generate_cover_letter
from app.services.hh_parser import HHParser

logger = logging.getLogger(__name__)


def run_async(coro):
    """Вспомогательная функция для запуска асинхронной корутины в синхронной Celery-задаче."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ---------- Парсинг всех новых вакансий (общий) ----------
@celery_app.task
def parse_all_vacancies():
    """Собирает вакансии по фильтрам всех активных аккаунтов и сохраняет в общую таблицу vacancies."""
    run_async(_parse_all_vacancies())


async def _parse_all_vacancies():
    async with AsyncSessionLocal() as session:
        # Получаем всех активных аккаунтов
        result = await session.execute(select(Account).where(Account.is_active == True))
        accounts = result.scalars().all()

        # Для каждого аккаунта парсим его фильтр и собираем вакансии
        all_vacancies = []  # список словарей с данными вакансий
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

        # Удаляем дубликаты по hh_id
        unique_vacs = {v["id"]: v for v in all_vacancies if v.get("id")}.values()

        # Для каждой вакансии проверяем, есть ли уже в БД, если нет — парсим детально и сохраняем
        for vac_data in unique_vacs:
            # Проверяем, существует ли уже вакансия с таким hh_id
            existing = await session.execute(
                select(Vacancy).where(Vacancy.hh_id == vac_data["id"])
            )
            if existing.scalar_one_or_none():
                continue

            # Парсим детали вакансии
            proxy = get_proxy_for_account(0)  # можно использовать любой прокси
            parser = HHParser(account_id=0, proxy=proxy)
            try:
                details = await parser.parse_vacancy_details(vac_data["link"])
                if "error" in details:
                    logger.error(f"Error parsing details for {vac_data['link']}: {details['error']}")
                    continue
            except Exception as e:
                logger.error(f"Exception parsing details for {vac_data['link']}: {e}")
                continue

            # Фильтрация по ключевым словам (можно заменить на LLM)
            if not is_backend_python_keywords(vac_data["title"], details.get("description", "")):
                logger.info(f"Vacancy {vac_data['title']} does not match backend Python, skipping")
                continue

            # Извлекаем проверочное слово (сначала regex, потом, если не найдено, через LLM)
            description = details.get("description", "")
            secret = extract_secret_word(description)
            if not secret and description:
                # Резервный вариант: запрос к LLM
                secret = await _extract_secret_word_llm(description)

            # Сохраняем вакансию
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
    """Использует Ollama для поиска проверочного слова."""
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
    """Для каждого аккаунта выбирает случайные вакансии, генерирует письма и отправляет (с учётом лимитов)."""
    run_async(_generate_and_send_responses())


def is_working_hours(account: Account) -> bool:
    msk_tz = pytz.timezone('Europe/Moscow')
    now_msk = datetime.now(msk_tz)
    hour = now_msk.hour
    return account.work_start_hour <= hour < account.work_end_hour


async def _generate_and_send_responses():
    async with AsyncSessionLocal() as session:
        accounts = await session.execute(select(Account).where(Account.is_active == True))
        accounts = accounts.scalars().all()

        for account in accounts:
            if not is_working_hours(account):
                continue
            await _reset_daily_limit_if_needed(account, session)

            remaining = account.daily_response_limit - account.responses_today
            if remaining <= 0:
                continue

            # Выбираем вакансии, на которые ещё не откликались
            subq_all = select(AccountVacancy.vacancy_id).where(AccountVacancy.account_id == account.id)
            stmt = select(Vacancy).where(Vacancy.id.not_in(subq_all)).order_by(func.random()).limit(remaining)
            vacancies = await session.execute(stmt)
            vacancies = vacancies.scalars().all()
            if not vacancies:
                continue

            auth_failed = False
            for vacancy in vacancies:
                if auth_failed:
                    break  # после ошибки авторизации не пытаемся отправить другие вакансии

                # Создаём запись о просмотре
                account_vacancy = AccountVacancy(
                    account_id=account.id,
                    vacancy_id=vacancy.id,
                    viewed_at=datetime.utcnow(),
                    responded=False
                )
                session.add(account_vacancy)
                await session.commit()

                # Генерируем письмо
                try:
                    letter = await generate_cover_letter(
                        vacancy_title=vacancy.title,
                        vacancy_description=vacancy.description,
                        company="Компания",
                        resume_text=account.resume_text,
                        secret_word=vacancy.check_word
                    )
                except Exception as e:
                    logger.error(f"Failed to generate letter for vacancy {vacancy.id}: {e}")
                    await session.delete(account_vacancy)
                    await session.commit()
                    continue

                # Сохраняем отклик
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

                # Отправляем отклик
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
                    # Отправляем уведомление в Telegram
                    await send_telegram_message(
                        account.id,
                        f"⚠️ Ошибка при отправке отклика на вакансию «{vacancy.title}».\n"
                        f"Причина: {str(e)[:200]}\n"
                        f"Проверьте настройки аккаунта (логин/пароль) и повторите попытку."
                    )
                    auth_failed = True  # прекращаем дальнейшие попытки для этого аккаунта
                finally:
                    await session.commit()

                # Если лимит не исчерпан и ошибки не было – делаем паузу
                if not auth_failed and account.responses_today < account.daily_response_limit:
                    delay = random.randint(account.response_interval_min, account.response_interval_max)
                    logger.info(f"Account {account.id}: waiting {delay} seconds before next response")
                    await asyncio.sleep(delay)

            logger.info(f"Account {account.id}: generated {account.responses_today} responses today.")


# async def _generate_and_send_responses():
#     async with AsyncSessionLocal() as session:
#         # Получаем всех активных аккаунтов
#         result = await session.execute(select(Account).where(Account.is_active == True))
#         accounts = result.scalars().all()
#
#         for account in accounts:
#             # Проверка рабочего времени
#             if not is_working_hours(account):
#                 logger.info(f"Account {account.id} skipped: outside working hours")
#                 continue
#             # Сброс лимита, если начался новый день
#             await _reset_daily_limit_if_needed(account, session)
#
#             # Сколько ещё можно откликнуться сегодня
#             remaining = account.daily_response_limit - account.responses_today
#             if remaining <= 0:
#                 logger.info(
#                     f"Account {account.id} has reached daily limit ({account.responses_today}/{account.daily_response_limit})")
#                 continue
#
#             # Выбираем вакансии, на которые этот аккаунт ещё не откликался (responded=False)
#             # Но также нужно учесть, что вакансия может быть уже просмотрена, но не отвечена
#             subq = select(AccountVacancy.vacancy_id).where(
#                 AccountVacancy.account_id == account.id,
#                 AccountVacancy.responded == False
#             )
#             # Берём вакансии, которых нет в подзапросе (т.е. ещё не просмотрены) – это новые
#             # Но также можно брать и те, где responded=False, но они уже есть в AccountVacancy – это неотвеченные ранее
#             # Для простоты возьмём все вакансии, которых нет в AccountVacancy для этого аккаунта
#             subq_all = select(AccountVacancy.vacancy_id).where(AccountVacancy.account_id == account.id)
#             stmt = select(Vacancy).where(Vacancy.id.not_in(subq_all)).order_by(func.random()).limit(remaining)
#             vacancies = await session.execute(stmt)
#             vacancies = vacancies.scalars().all()
#
#             if not vacancies:
#                 logger.info(f"No new vacancies for account {account.id}")
#                 continue
#
#             for vacancy in vacancies:
#                 # Создаём запись о просмотре (responded=False)
#                 account_vacancy = AccountVacancy(
#                     account_id=account.id,
#                     vacancy_id=vacancy.id,
#                     viewed_at=datetime.utcnow(),
#                     responded=False
#                 )
#                 session.add(account_vacancy)
#                 await session.commit()  # коммитим, чтобы зафиксировать просмотр
#
#                 # Генерируем сопроводительное письмо
#                 try:
#                     letter = await generate_cover_letter(
#                         vacancy_title=vacancy.title,
#                         vacancy_description=vacancy.description,
#                         company="Компания",  # можно достать из вакансии
#                         resume_text=account.resume_text,
#                         secret_word=vacancy.check_word
#                     )
#                 except Exception as e:
#                     logger.error(f"Failed to generate letter for vacancy {vacancy.id}: {e}")
#                     # Удаляем запись просмотра, чтобы можно было повторить позже
#                     await session.delete(account_vacancy)
#                     await session.commit()
#                     continue
#
#                 # Сохраняем отклик
#                 response = Response(
#                     account_id=account.id,
#                     vacancy_id=vacancy.id,
#                     cover_letter=letter,
#                     status="pending"
#                 )
#                 session.add(response)
#                 await session.commit()
#                 await session.refresh(response)
#
#                 # Обновляем запись AccountVacancy: отмечаем, что отклик создан
#                 account_vacancy.responded = True
#                 account_vacancy.response_id = response.id
#                 await session.commit()
#
#                 # Увеличиваем счётчик откликов за сегодня
#                 account.responses_today += 1
#                 await session.commit()
#
#                 # Отправляем отклик
#                 try:
#                     success = await send_response(account.id, vacancy.id, response.id)
#                     if success:
#                         response.status = "sent"
#                         response.sent_at = datetime.utcnow()
#                         logger.info(f"Response {response.id} sent for account {account.id}")
#                     else:
#                         response.status = "error"
#                         response.error_message = "send_response returned False"
#                 except Exception as e:
#                     logger.error(f"Failed to send response {response.id}: {e}")
#                     response.status = "error"
#                     response.error_message = str(e)
#                 finally:
#                     await session.commit()
#
#                 # Если лимит ещё не исчерпан, делаем паузу перед следующей вакансией
#                 if account.responses_today < account.daily_response_limit:
#                     delay = random.randint(account.response_interval_min, account.response_interval_max)
#                     logger.info(f"Account {account.id}: waiting {delay} seconds before next response")
#                     await asyncio.sleep(delay)
#
#             logger.info(f"Account {account.id}: generated {account.responses_today} responses today.")


async def _reset_daily_limit_if_needed(account: Account, session: AsyncSession):
    """Сбрасывает счётчик откликов, если сегодня новый день."""
    today = date.today()
    if account.last_reset_date < today:
        account.responses_today = 0
        # Генерируем новый лимит на сегодня
        account.daily_response_limit = random.randint(account.daily_limit_min, account.daily_limit_max)
        account.last_reset_date = today
        await session.commit()
        logger.info(f"Account {account.id} new daily limit: {account.daily_response_limit}")


# ---------- Отдельная задача для сброса лимитов ----------
@celery_app.task
def reset_daily_limits():
    """Принудительно сбрасывает лимиты для всех аккаунтов (запускается раз в день)."""
    run_async(_reset_daily_limits())


async def _reset_daily_limits():
    async with AsyncSessionLocal() as session:
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
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            await send_telegram_message(chat_id, "❌ Аккаунт не найден.")
            return

        # Получаем настройки
        test_parse = account.test_parse_vacancy
        test_generate = account.test_generate_letter
        test_send = account.test_send_response
        test_count = account.test_count

        # Формируем отчёт
        report_lines = [
            f"<b>Тестовый запуск для аккаунта {account.username}</b>",
            f"Настройки: парсинг={'✅' if test_parse else '❌'}, "
            f"генерация={'✅' if test_generate else '❌'}, "
            f"отправка={'✅' if test_send else '❌'}",
            f"Количество тестов: {test_count}"
        ]

        # Имитация выполнения
        for i in range(1, test_count + 1):
            step_report = []
            if test_parse:
                step_report.append("парсинг OK")
            if test_generate:
                step_report.append("генерация OK")
            if test_send:
                step_report.append("отправка OK")
            report_lines.append(f"Тест {i}: {', '.join(step_report)}")

        await send_telegram_message(chat_id, "\n".join(report_lines))


# ---------- Парсинг новых вакансий для конкретного аккаунта ----------
@celery_app.task
def parse_new_vacancies_for_account(account_id: int):
    """Парсит новые вакансии для конкретного аккаунта (по его фильтру)."""
    run_async(_parse_new_vacancies_for_account(account_id))


async def _parse_new_vacancies_for_account(account_id: int):
    async with AsyncSessionLocal() as session:
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

        # Сохраняем только новые вакансии (которых нет в общей таблице)
        for vac_data in vacancies:
            if not vac_data.get("id"):
                continue
            existing = await session.execute(
                select(Vacancy).where(Vacancy.hh_id == vac_data["id"])
            )
            if existing.scalar_one_or_none():
                continue

            # Парсим детали
            try:
                details = await parser.parse_vacancy_details(vac_data["link"])
                if "error" in details:
                    continue
            except Exception as e:
                logger.error(f"Error parsing details for {vac_data['link']}: {e}")
                continue

            # Фильтрация по ключевым словам
            if not is_backend_python_keywords(vac_data["title"], details.get("description", "")):
                continue

            # Сохраняем
            new_vac = Vacancy(
                hh_id=vac_data["id"],
                title=vac_data["title"],
                url=vac_data["link"],
                description=details.get("description", ""),
                check_word=extract_secret_word(details.get("description", ""))
            )
            session.add(new_vac)
            await session.commit()
            logger.info(f"Saved new vacancy {vac_data['id']} for account {account_id}")
