import logging
import random
from datetime import date
from typing import Optional

from sqlalchemy import select, update

from app.database.models import Account
from app.services.base import (
    with_session,
    get_object,
    update_object,
    create_object,
    list_objects)

from app.services.exceptions import ObjectNotFound, ObjectAlreadyExists
from app.utils.encryption import encrypt_password

logger = logging.getLogger(__name__)


# ---------- Получение аккаунта с проверкой ----------
@with_session
async def get_account(session, account_id: int) -> Optional[Account]:
    """Возвращает аккаунт или None."""
    return await get_object(session, Account, account_id)


@with_session
async def get_account_or_raise(session, account_id: int) -> Account:
    """Возвращает аккаунт или выбрасывает ObjectNotFound."""
    return await get_object(session, Account, account_id, raise_if_not_found=True)


# ---------- Создание ----------
@with_session
async def create_account(session, data: dict) -> Account:
    """Создаёт новый аккаунт."""
    # Проверяем, не существует ли уже
    existing = await get_object(session, Account, data['account_id'])
    if existing:
        logger.error(f"Account with id {data['account_id']} already exists")
        raise ObjectAlreadyExists(f"Account with id {data['account_id']} already exists")

    account = Account(
        id=data['account_id'],
        username=data['username'],
        password_encrypted=data['password_encrypted'],
        resume_id=data['resume_id'],
        proxy=data.get('proxy'),
        search_filter={"url": data['filter_url']},
        max_pages=2,
        daily_limit_min=50,
        daily_limit_max=100,
    )
    # Устанавливаем случайный дневной лимит
    account.daily_response_limit = random.randint(account.daily_limit_min, account.daily_limit_max)
    return await create_object(session, Account, **account.__dict__)  # упрощённо, лучше передавать kwargs


# ---------- Обновления ----------
@with_session
async def update_account_filter(session, account_id: int, new_url: str) -> Account:
    account = await get_account_or_raise(session, account_id)
    current = account.search_filter or {}
    current["url"] = new_url
    return await update_object(session, account, search_filter=current)


@with_session
async def update_account_resume(session, account_id: int, new_resume: str) -> Account:
    account = await get_account_or_raise(session, account_id)
    return await update_object(session, account, resume_text=new_resume)


@with_session
async def update_account_proxy(session, account_id: int, new_proxy: Optional[str]) -> Account:
    account = await get_account_or_raise(session, account_id)
    # Сбрасываем cookies при смене прокси
    await update_object(session, account, proxy=new_proxy, cookies={})
    return account


@with_session
async def update_account_credentials(session, account_id: int, username: str, password: str) -> Account:
    account = await get_account_or_raise(session, account_id)
    encrypted = encrypt_password(password)
    await update_object(session, account, username=username, password_encrypted=encrypted, cookies={})
    return account


@with_session
async def update_account_limit_range(session, account_id: int, min_lim: int, max_lim: int) -> Account:
    account = await get_account_or_raise(session, account_id)
    new_limit = random.randint(min_lim, max_lim)
    return await update_object(
        session,
        account,
        daily_limit_min=min_lim,
        daily_limit_max=max_lim,
        daily_response_limit=new_limit
    )


@with_session
async def update_account_interval_range(session, account_id: int, min_int: int, max_int: int) -> Account:
    account = await get_account_or_raise(session, account_id)
    return await update_object(
        session,
        account,
        response_interval_min=min_int,
        response_interval_max=max_int
    )


@with_session
async def update_account_work_hours(session, account_id: int, start: int, end: int) -> Account:
    account = await get_account_or_raise(session, account_id)
    return await update_object(session, account, work_start_hour=start, work_end_hour=end)


@with_session
async def update_account_telegram_username(session, account_id: int, tg_username: Optional[str]) -> Account:
    account = await get_account_or_raise(session, account_id)
    return await update_object(session, account, telegram_username=tg_username)


@with_session
async def update_account_max_pages(session, account_id: int, max_pages: int) -> Account:
    account = await get_account_or_raise(session, account_id)
    return await update_object(session, account, max_pages=max_pages)


@with_session
async def update_test_flags(session, account_id: int, flag: str):
    account = await get_account_or_raise(session, account_id)
    if flag == "parse":
        account.test_parse_vacancy = not account.test_parse_vacancy
    elif flag == "generate":
        account.test_generate_letter = not account.test_generate_letter
    elif flag == "send":
        account.test_send_response = not account.test_send_response
    await session.commit()
    return account


@with_session
async def update_test_count(session, account_id: int, count: int):
    account = await get_account_or_raise(session, account_id)
    account.test_count = count
    await session.commit()
    return account


# ---------- Получение всех аккаунтов ----------
@with_session
async def get_all_accounts(session):
    """Возвращает список всех аккаунтов."""
    return await list_objects(session, Account)


# ---------- Сброс дневного лимита ----------
@with_session
async def reset_daily_limit_if_needed(session, account: Account) -> bool:
    today = date.today()
    if account.last_reset_date < today:
        account.responses_today = 0
        account.daily_response_limit = random.randint(account.daily_limit_min, account.daily_limit_max)
        account.last_reset_date = today
        await session.commit()
        logger.info(f"Account {account.id} daily limit reset to {account.daily_response_limit}")
        return True
    return False


@with_session
async def get_account_with_reset(session, account_id: int) -> Optional[Account]:
    """Получает аккаунт и сбрасывает дневной лимит при необходимости."""
    account = await get_account_or_raise(session, account_id)
    await reset_daily_limit_if_needed(session, account)
    return account
