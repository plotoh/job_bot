"""
Асинхронный клиент для hh.ru на основе Playwright.
Использует реальный браузер для обхода защиты и получения динамического контента.
"""

import asyncio
import json
import logging
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright, Browser, Page, ProxySettings

from .exceptions import (
    HHError,
    HHAuthError,
    HHNetworkError,
    HHRateLimitError,
    HHParseError,
)
from .models import VacancyPreview, VacancyDetails, ApplyResult
from .utils import extract_json_from_html, extract_description, extract_skills

logger = logging.getLogger(__name__)


class HHClient:
    """
    Асинхронный клиент для hh.ru на основе Playwright.
    Поддерживает те же методы, что и предыдущая версия.
    """

    BASE_URL = "https://hh.ru"

    def __init__(self, cookies: Dict[str, str], proxy: Optional[str] = None):
        """
        :param cookies: Словарь cookies (например, полученные после логина).
        :param proxy: Прокси в формате "http://user:pass@host:port".
        """
        self._cookies = cookies
        self._proxy = proxy
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._context = None

    async def __aenter__(self):
        await self._init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _init_browser(self):
        """Инициализирует браузер, контекст с cookies и прокси, открывает новую страницу."""
        self._playwright = await async_playwright().start()

        # Настройка прокси, если задан
        proxy_settings = None
        if self._proxy:
            # Парсим строку прокси (ожидается http://user:pass@host:port или host:port)
            match = re.match(
                r'(?:(?P<protocol>\w+)://)?(?:(?P<user>[^:]+):(?P<pass>[^@]+)@)?(?P<host>[^:]+):(?P<port>\d+)',
                self._proxy
            )
            if match:
                proxy_settings = ProxySettings(
                    server=f"{match.group('protocol') or 'http'}://{match.group('host')}:{match.group('port')}",
                    username=match.group('user'),
                    password=match.group('pass')
                )
            else:
                # Простой формат host:port
                host, port = self._proxy.split(':')
                proxy_settings = ProxySettings(server=f"http://{host}:{port}")

        # Запуск браузера (headless=True для сервера)
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            proxy=proxy_settings,
            args=['--disable-blink-features=AutomationControlled']  # скрываем автоматизацию
        )

        # Создаём контекст с увеличенным размером shared memory для избежания ошибок
        self._context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # Добавляем cookies
        if self._cookies:
            # Playwright требует список словарей с определёнными полями
            cookies_list = [
                {
                    "name": name,
                    "value": value,
                    "domain": ".hh.ru",
                    "path": "/",
                    "secure": False,
                    "httpOnly": False,
                    "sameSite": "Lax"
                }
                for name, value in self._cookies.items()
            ]
            await self._context.add_cookies(cookies_list)

        self._page = await self._context.new_page()
        logger.debug("HHClient (Playwright) initialized with cookies: %s", list(self._cookies.keys()))

    async def close(self):
        """Корректно закрывает все ресурсы."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.debug("HHClient (Playwright) closed")

    async def _goto(self, url: str, wait_until: str = "networkidle") -> str:
        """
        Переходит по URL и возвращает HTML страницы.
        wait_until может быть "load", "domcontentloaded", "networkidle".
        """
        if not self._page:
            raise HHNetworkError("Browser not initialized")
        try:
            logger.debug("Navigating to %s", url)
            response = await self._page.goto(url, wait_until=wait_until, timeout=30000)
            if not response:
                raise HHNetworkError("No response from page.goto")
            status = response.status
            if status >= 400:
                if status == 401:
                    raise HHAuthError("Unauthorized")
                elif status == 403:
                    raise HHAuthError("Forbidden")
                elif status == 429:
                    raise HHRateLimitError("Rate limit exceeded")
                else:
                    raise HHNetworkError(f"HTTP error {status}")
            # Ждём немного, чтобы убедиться, что динамический контент загрузился
            await self._page.wait_for_timeout(500)
            html = await self._page.content()
            return html
        except Exception as e:
            raise HHNetworkError(f"Navigation error: {e}")

    @property
    def xsrf_token(self) -> Optional[str]:
        """Возвращает значение cookie _xsrf, если есть."""
        return self._cookies.get("_xsrf")

    # === Публичные методы ===

    async def search_vacancies(self, search_url: str, max_pages: int = 1) -> List[VacancyPreview]:
        """
        Ищет вакансии по заданному URL поиска, перебирая страницы.
        Возвращает список VacancyPreview.
        """
        parsed = urlparse(search_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        params = parse_qs(parsed.query)
        # Преобразуем значения из списков в строки
        flat_params = {k: v[0] for k, v in params.items()}

        vacancies = []
        last_page = 0
        for page in range(max_pages):
            page_params = flat_params.copy()
            page_params["page"] = str(page)
            # Строим URL с параметрами
            query = "&".join(f"{k}={v}" for k, v in page_params.items())
            url = f"{base_url}?{query}"

            try:
                html = await self._goto(url, wait_until="domcontentloaded")
            except HHError as e:
                logger.error("Failed to load search page %d: %s", page, e)
                break

            logger.info("Search page %d loaded, length=%d", page, len(html))

            # Сохраняем HTML для отладки (если уровень DEBUG)
            if logger.isEnabledFor(logging.DEBUG):
                with open(f"debug_search_page_{page}.html", "w", encoding="utf-8") as f:
                    f.write(html)

            try:
                page_vacancies = extract_json_from_html(html, "vacancies")
            except HHParseError as e:
                logger.error("Failed to extract vacancies from page %d: %s", page, e)
                # Если не удалось найти вакансии, возможно, страница изменилась – пробуем найти данные в другом месте
                # Например, в window.__INITIAL_STATE__ (но это потребует дополнительного парсинга)
                # Пока просто прерываем
                break

            for raw in page_vacancies:
                try:
                    vacancy = VacancyPreview.model_validate(raw)
                    vacancies.append(vacancy)
                except Exception as e:
                    logger.warning("Failed to parse vacancy: %s", e, exc_info=True)
            last_page = page
            # Задержка между страницами, чтобы не нагружать сервер
            await asyncio.sleep(2)

        logger.info("Found %d vacancies across %d pages", len(vacancies), last_page + 1)
        return vacancies

    async def get_vacancy_details(self, vacancy_id: int) -> VacancyDetails:
        """
        Получает детальную информацию о вакансии.
        """
        url = f"{self.BASE_URL}/vacancy/{vacancy_id}"
        html = await self._goto(url, wait_until="networkidle")
        description = extract_description(html)
        skills = extract_skills(html)
        return VacancyDetails(
            description=description,
            skills=skills,
            full_html=html
        )

    async def get_vacancy_tests(self, vacancy_id: int) -> Dict[str, Any]:
        """
        Получает данные о тесте для вакансии (если есть).
        Возвращает словарь с полями uidPk, guid, startTime, tasks и т.д.
        """
        url = f"{self.BASE_URL}/applicant/vacancy_response?vacancyId={vacancy_id}&startedWithQuestion=false"
        html = await self._goto(url, wait_until="networkidle")
        tests_data = extract_json_from_html(html, "vacancyTests")
        return tests_data.get(str(vacancy_id), {})

    async def apply(self, vacancy_id: int, resume_hash: str, letter: str = "") -> ApplyResult:
        """
        Отправляет отклик на вакансию через браузер.
        """
        vacancy_url = f"{self.BASE_URL}/vacancy/{vacancy_id}"
        await self._goto(vacancy_url, wait_until="networkidle")

        # Ищем кнопку отклика (селектор может меняться, но обычно это a с data-qa="vacancy-response-link")
        response_button = await self._page.query_selector('a[data-qa="vacancy-response-link"]')
        if not response_button:
            # Если не нашли, возможно, это другая страница или уже откликнулись
            logger.error("Response button not found for vacancy %d", vacancy_id)
            raise HHParseError("Response button not found")

        await response_button.click()
        await self._page.wait_for_load_state("networkidle")

        # Если есть поле для сопроводительного письма, заполняем
        letter_field = await self._page.query_selector('textarea[data-qa="vacancy-response-letter"]')
        if letter_field and letter:
            await letter_field.fill(letter)

        # Ищем кнопку отправки (обычно button с data-qa="vacancy-response-submit")
        submit_button = await self._page.query_selector('button[data-qa="vacancy-response-submit"]')
        if not submit_button:
            logger.error("Submit button not found for vacancy %d", vacancy_id)
            raise HHParseError("Submit button not found")

        await submit_button.click()
        await self._page.wait_for_load_state("networkidle")

        # Проверяем результат – обычно появляется сообщение об успехе или ошибке
        html = await self._page.content()
        if "Ваш отклик отправлен" in html or "success" in html:
            logger.info("Successfully applied to vacancy %d", vacancy_id)
            return ApplyResult(success=True)
        else:
            # Ищем сообщение об ошибке
            error_elem = await self._page.query_selector('div[data-qa="vacancy-response-error"]')
            error_text = await error_elem.text_content() if error_elem else "Unknown error"
            if "negotiations-limit-exceeded" in error_text:
                logger.warning("Daily limit exceeded on hh.ru for vacancy %d", vacancy_id)
                return ApplyResult(success=False, error=error_text, limit_exceeded=True)
            logger.error("Failed to apply to vacancy %d: %s", vacancy_id, error_text)
            return ApplyResult(success=False, error=error_text)

    async def is_logged_in(self) -> bool:
        """
        Проверяет, валидны ли текущие cookies, загружая страницу резюме.
        """
        try:
            html = await self._goto(f"{self.BASE_URL}/applicant/resumes", wait_until="domcontentloaded")
            # Наличие 'latestResumeHash' говорит о том, что мы авторизованы
            return 'latestResumeHash' in html
        except HHAuthError:
            return False
        except Exception:
            return False

    async def login(self, username: str, password: str) -> Dict[str, str]:
        """
        Выполняет вход на hh.ru через браузер и возвращает новые cookies.
        """
        # Открываем страницу логина
        await self._goto(f"{self.BASE_URL}/account/login", wait_until="networkidle")

        # Заполняем форму
        await self._page.fill('input[name="username"]', username)
        await self._page.fill('input[name="password"]', password)
        await self._page.click('button[type="submit"]')
        await self._page.wait_for_load_state("networkidle")

        # Проверяем успешность – после успешного входа обычно редирект на главную
        if self._page.url == f"{self.BASE_URL}/":
            # Получаем cookies из контекста
            cookies = await self._context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}
            logger.info("Login successful for user %s", username)
            return cookie_dict
        else:
            # Возможно, появилось сообщение об ошибке
            error_elem = await self._page.query_selector('.error, .alert')
            error_text = await error_elem.text_content() if error_elem else "Unknown error"
            logger.error("Login failed for user %s: %s", username, error_text)
            raise HHAuthError(f"Login failed: {error_text}")