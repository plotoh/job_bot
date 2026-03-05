import random
from typing import Optional
from datetime import date

from sqlalchemy import select
from app.database.models import AsyncSessionLocal, Account
from app.utils.db import get_session  # мы создадим ниже
from app.utils.encryption import encrypt_password





async def get_account(account_id: int) -> Optional[Account]:
    async with AsyncSessionLocal() as session:
        return await session.get(Account, account_id)


async def get_all_accounts():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account))
        return result.scalars().all()


async def update_account_prompt(account_id: int, prompt: str) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        account.system_prompt = prompt
        await session.commit()
        return True


async def update_account_filter(account_id: int, new_url: str) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        current = account.search_filter or {}
        current["url"] = new_url
        account.search_filter = current
        await session.commit()
        return True


async def update_account_resume(account_id: int, new_resume: str) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        account.resume_text = new_resume
        await session.commit()
        return True


async def update_account_proxy(account_id: int, new_proxy: Optional[str]) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        account.proxy = new_proxy
        account.cookies = {}  # сбрасываем сессию
        await session.commit()
        return True


async def update_account_credentials(account_id: int, username: str, password: str) -> bool:
    encrypted = encrypt_password(password)
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        account.username = username
        account.password_encrypted = encrypted
        account.cookies = {}
        await session.commit()
        return True


async def update_account_limit(account_id: int, new_limit: int) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        account.daily_response_limit = new_limit
        await session.commit()
        return True


async def update_account_limit_range(account_id: int, min_lim: int, max_lim: int) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        account.daily_limit_min = min_lim
        account.daily_limit_max = max_lim
        # можно сразу обновить текущий лимит случайным числом из нового диапазона
        account.daily_response_limit = random.randint(min_lim, max_lim)
        await session.commit()
        return True


async def update_account_interval_range(account_id: int, min_int: int, max_int: int) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        account.response_interval_min = min_int
        account.response_interval_max = max_int
        await session.commit()
        return True


async def update_account_work_hours(account_id: int, start: int, end: int) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account:
            return False
        account.work_start_hour = start
        account.work_end_hour = end
        await session.commit()
        return True


async def create_account(data: dict) -> bool:
    """Создаёт новый аккаунт из словаря с полями."""
    async with AsyncSessionLocal() as session:
        account = Account(
            id=data['account_id'],
            username=data['username'],
            password_encrypted=data['password_encrypted'],
            resume_id=data['resume_id'],
            proxy=data.get('proxy'),
            search_filter={"url": data['filter_url'], "max_pages": data['max_pages']},
        )
        session.add(account)
        await session.commit()
        return True
