# app/worker/tasks.py
import asyncio
import logging
from datetime import date, datetime
from typing import Optional

import aiohttp
import pytz
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.database.models import Account, Response, AccountVacancy
from app.services.vacancy import fetch_and_save_new_vacancies
from app.services.response import process_pending_responses, is_working_hours
from app.services.account_crud import reset_daily_limit_if_needed
from app.utils.proxy_rotator import get_proxy_for_account
from app.utils.encryption import decrypt_password
from app.worker.celery_app import celery_app
from hh_client import HHClient

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


# ---------- Парсинг новых вакансий для одного аккаунта ----------
@celery_app.task
def parse_new_vacancies_for_account(account_id: int):
    logger.info("Starting parse_new_vacancies_for_account for account %d", account_id)
    run_async(_parse_for_account(account_id))


async def _parse_for_account(account_id: int):
    async with get_db_session()() as session:
        account = await session.get(Account, account_id)
        if not account or not account.is_active:
            logger.warning("Account %d not found or inactive", account_id)
            return

        try:
            count = await fetch_and_save_new_vacancies(account, session)
            logger.info("Account %d: saved %d new vacancies", account_id, count)
        except Exception as e:
            logger.error("Error in parse_for_account %d: %s", account_id, e, exc_info=True)


# ---------- Парсинг всех активных аккаунтов ----------
@celery_app.task
def parse_all_vacancies():
    logger.info("Starting parse_all_vacancies task")
    run_async(_parse_all_vacancies())


async def _parse_all_vacancies():
    async with get_db_session()() as session:
        accounts = await session.execute(select(Account).where(Account.is_active == True))
        accounts = accounts.scalars().all()
        logger.info("Found %d active accounts", len(accounts))

        for account in accounts:
            try:
                count = await fetch_and_save_new_vacancies(account, session)
                logger.info("Account %d: saved %d new vacancies", account.id, count)
            except Exception as e:
                logger.error("Error processing account %d: %s", account.id, e, exc_info=True)
                continue


# ---------- Генерация и отправка откликов ----------
@celery_app.task
def generate_and_send_responses():
    logger.info("Starting generate_and_send_responses task")
    run_async(_generate_and_send_responses())


async def _generate_and_send_responses():
    async with get_db_session()() as session:
        accounts = await session.execute(select(Account).where(Account.is_active == True))
        accounts = accounts.scalars().all()
        logger.info("Processing responses for %d accounts", len(accounts))

        for account in accounts:
            if not is_working_hours(account):
                logger.debug("Account %d is outside working hours, skipping", account.id)
                continue

            try:
                results = await process_pending_responses(account, session, test_mode=False)
                logger.info("Account %d: processed %d responses", account.id, len(results))
            except Exception as e:
                logger.error("Error processing responses for account %d: %s", account.id, e, exc_info=True)


# ---------- Сброс дневных лимитов ----------
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


# ---------- Тестовый запуск для аккаунта ----------
@celery_app.task
def run_test_for_account(account_id: int, chat_id: int):
    logger.info("Starting test for account %d, chat %d", account_id, chat_id)
    run_async(_run_test_for_account(account_id, chat_id))


async def _run_test_for_account(account_id: int, chat_id: int):
    async with get_db_session()() as session:
        account = await session.get(Account, account_id)
        if not account:
            await send_telegram_message(chat_id, "❌ Аккаунт не найден.")
            logger.error("Account %d not found for test", account_id)
            return

        # Сбрасываем лимит на всякий случай (чтобы не мешал)
        await reset_daily_limit_if_needed(account, session)

        try:
            results = await process_pending_responses(account, session, test_mode=True)
        except Exception as e:
            logger.error("Test failed for account %d: %s", account_id, e, exc_info=True)
            await send_telegram_message(chat_id, f"❌ Ошибка при тестировании: {e}")
            return

        if not results:
            await send_telegram_message(chat_id, "ℹ️ Нет новых вакансий для тестирования.")
            return

        report = [f"<b>Тестовый запуск для аккаунта {account.username}</b>"]
        report.append(f"Настройки: парсинг={'✅' if account.test_parse_vacancy else '❌'}, "
                      f"генерация={'✅' if account.test_generate_letter else '❌'}, "
                      f"отправка={'✅' if account.test_send_response else '❌'}")
        report.append(f"Количество тестов: {len(results)}\n")

        for i, res in enumerate(results, 1):
            if res["success"]:
                report.append(f"✅ <b>{i}. {res['title']}</b>")
            else:
                report.append(f"❌ <b>{i}. {res['title']}</b> (ошибка)")
            report.append(f"🔗 {res['url']}\n")

        full_text = "\n".join(report)
        if len(full_text) > 4000:
            for i in range(0, len(full_text), 4000):
                await send_telegram_message(chat_id, full_text[i:i + 4000])
        else:
            await send_telegram_message(chat_id, full_text)


# ---------- Обновление cookies для всех аккаунтов ----------
@celery_app.task
def refresh_all_cookies():
    logger.info("Starting refresh_all_cookies task")
    run_async(_refresh_all_cookies())


async def _refresh_all_cookies():
    async with get_db_session()() as session:
        accounts = await session.execute(select(Account))
        accounts = accounts.scalars().all()
        for account in accounts:
            need_refresh = False
            if not account.cookies:
                need_refresh = True
            elif hasattr(account, 'cookies_updated_at') and account.cookies_updated_at:
                age = datetime.utcnow() - account.cookies_updated_at
                if age.total_seconds() > 12 * 3600:
                    need_refresh = True
            else:
                # Проверка через is_logged_in
                try:
                    async with HHClient(account.cookies or {}, account.proxy) as client:
                        if not await client.is_logged_in():
                            need_refresh = True
                except Exception:
                    need_refresh = True

            if need_refresh:
                try:
                    logger.info("Refreshing cookies for account %d", account.id)
                    # Создаём временный клиент без cookies для логина
                    temp_client = HHClient({}, account.proxy)
                    await temp_client._create_session()
                    new_cookies = await temp_client.login(
                        account.username,
                        decrypt_password(account.password_encrypted)
                    )
                    await temp_client.close()

                    account.cookies = new_cookies
                    if hasattr(account, 'cookies_updated_at'):
                        account.cookies_updated_at = datetime.utcnow()
                    await session.commit()
                    logger.info("Cookies refreshed for account %d", account.id)
                except Exception as e:
                    logger.error("Failed to refresh cookies for account %d: %s", account.id, e)
