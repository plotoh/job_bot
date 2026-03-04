import logging
import asyncio

from playwright.async_api import async_playwright

from app.database.models import AsyncSessionLocal, Account, Response, Vacancy
from app.utils.proxy_rotator import get_proxy_for_account
from app.utils.encryption import decrypt_password

logger = logging.getLogger(__name__)


async def ensure_cookies(account: Account):
    """Проверяет наличие cookies, при необходимости выполняет вход и сохраняет новые cookies."""
    if account.cookies:
        # Можно проверить валидность, попытавшись открыть страницу, но для простоты считаем, что ок
        return account.cookies

    # Выполняем вход
    async with async_playwright() as p:
        proxy = get_proxy_for_account(account.id)
        browser = await p.chromium.launch(headless=True, proxy=proxy)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Переходим на страницу входа
            await page.goto("https://hh.ru/account/login", wait_until="domcontentloaded")
            # Заполняем форму (селекторы могут меняться)
            await page.fill('input[name="username"]', account.username)
            password = decrypt_password(account.password_encrypted)
            await page.fill('input[name="password"]', password)
            await page.click('button[data-qa="account-login-submit"]')
            # Ждём перехода на главную или появления признака авторизации
            await page.wait_for_selector('[data-qa="main-page"]', timeout=10000)
            # Сохраняем cookies
            cookies = await context.cookies()
            account.cookies = cookies
            async with AsyncSessionLocal() as session:
                await session.merge(account)
                await session.commit()
            return cookies
        except Exception as e:
            logger.error(f"Login failed for account {account.id}: {e}")
            raise
        finally:
            await browser.close()


async def send_response(account_id: int, vacancy_id: int, response_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        vacancy = await session.get(Vacancy, vacancy_id)
        response = await session.get(Response, response_id)

        if not account or not vacancy or not response:
            raise ValueError("Account, vacancy or response not found")

        # Получаем актуальные cookies (авторизуемся при необходимости)
        cookies = await ensure_cookies(account)

        proxy = get_proxy_for_account(account_id)

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy=proxy
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            await context.add_cookies(cookies)

            page = await context.new_page()
            await page.goto(vacancy.url, wait_until="domcontentloaded", timeout=30000)

            # Жмём кнопку отклика
            try:
                await page.wait_for_selector('[data-qa="vacancy-response-button"]', timeout=10000)
                await page.click('[data-qa="vacancy-response-button"]')
            except Exception as e:
                logger.error(f"Response button not found: {e}")
                await browser.close()
                raise

            # Заполняем письмо
            try:
                await page.wait_for_selector('[data-qa="response-letter-field"]', timeout=10000)
                await page.fill('[data-qa="response-letter-field"]', response.cover_letter)
            except Exception as e:
                logger.error(f"Letter field not found: {e}")
                await browser.close()
                raise

            # Отправляем
            try:
                await page.click('[data-qa="response-submit-button"]')
                await page.wait_for_selector('[data-qa="response-success-message"]', timeout=10000)
            except Exception as e:
                logger.error(f"Submission failed: {e}")
                await browser.close()
                raise

            # Обновляем cookies (на случай, если они изменились)
            new_cookies = await context.cookies()
            account.cookies = new_cookies
            async with AsyncSessionLocal() as update_session:
                await update_session.merge(account)
                await update_session.commit()

            await browser.close()
            logger.info(f"Response {response_id} sent successfully")
            return True