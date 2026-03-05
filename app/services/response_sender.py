import logging
from datetime import datetime
from typing import Dict, Optional

from app.database.models import AsyncSessionLocal, Account, Response, Vacancy
from app.services.hh_api import HHApiClient
from app.services.login import login_and_get_cookies
from app.utils.proxy_rotator import get_proxy_for_account
from app.utils.encryption import decrypt_password

logger = logging.getLogger(__name__)


async def ensure_cookies(account: Account) -> Dict[str, str]:
    """
    Проверяет валидность cookies, при необходимости обновляет их через логин.
    Возвращает словарь cookies.
    """
    if account.cookies:
        # Проверим, работают ли они (быстрый запрос)
        client = HHApiClient(
            account_id=account.id,
            cookies=account.cookies,
            resume_hash=account.resume_id,
            proxy=get_proxy_for_account(account.id)
        )
        if client.is_logged_in():
            return account.cookies

    # Нужно выполнить вход и получить новые cookies
    logger.info(f"Refreshing cookies for account {account.id}")
    new_cookies = await login_and_get_cookies(
        account.username,
        decrypt_password(account.password_encrypted)
    )
    if not new_cookies:
        raise Exception("Failed to login and obtain cookies")

    # Сохраняем в БД
    async with AsyncSessionLocal() as session:
        acc = await session.get(Account, account.id)
        acc.cookies = new_cookies
        await session.commit()

    return new_cookies


async def send_response(account_id: int, vacancy_id: int, response_id: int) -> bool:
    """
    Отправляет отклик через HTTP-клиент.
    """
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        vacancy = await session.get(Vacancy, vacancy_id)
        response = await session.get(Response, response_id)

        if not account or not vacancy or not response:
            raise ValueError("Account, vacancy or response not found")

        # Получаем валидные cookies
        cookies = await ensure_cookies(account)

        # Создаём клиент
        proxy = get_proxy_for_account(account_id)
        client = HHApiClient(
            account_id=account.id,
            cookies=cookies,
            resume_hash=account.resume_id,
            proxy=proxy
        )

        # Отправляем отклик
        success, error_msg = client.apply(
            vacancy_id=vacancy_id,
            vacancy_url=vacancy.url,
            letter=response.cover_letter
        )

        if success:
            logger.info(f"Response {response_id} sent successfully")
            response.status = "sent"
            response.sent_at = datetime.utcnow()
            await session.commit()
            return True
        else:
            logger.error(f"Failed to send response {response_id}: {error_msg}")
            response.status = "error"
            response.error_message = error_msg
            await session.commit()
            return False