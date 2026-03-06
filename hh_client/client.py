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
    Браузер и контекст создаются однократно и живут всё время жизни клиента.
    Для каждого запроса создаётся новая страница, которая закрывается после использования.
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
        self._context = None
        self._initialized = False

    async def __aenter__(self):
        await self._ensure_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _ensure_browser(self):
        """Инициализирует браузер и контекст, если они ещё не созданы."""
        if self._initialized:
            return

        self._playwright = await async_playwright().start()

        # Настройка прокси, если задан
        proxy_settings = None
        if self._proxy:
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
                host, port = self._proxy.split(':')
                proxy_settings = ProxySettings(server=f"http://{host}:{port}")

        self._browser = await self._playwright.chromium.launch(
            headless=True,
            proxy=proxy_settings,
            args=['--disable-blink-features=AutomationControlled']
        )
        logger.info("Browser launched")

        self._context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        logger.debug("Browser context created")

        # Добавляем cookies
        if self._cookies:
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
            logger.debug("Cookies added: %s", list(self._cookies.keys()))

        self._initialized = True

    async def close(self):
        """Закрывает все ресурсы (браузер, контекст, playwright)."""
        if self._context:
            await self._context.close()
            logger.debug("Context closed")
        if self._browser:
            await self._browser.close()
            logger.debug("Browser closed")
        if self._playwright:
            await self._playwright.stop()
            logger.debug("Playwright stopped")
        self._initialized = False

    async def _goto(self, page: Page, url: str, wait_until: str = "networkidle") -> str:
        """
        Переходит по URL на переданной странице и возвращает HTML.
        При ошибках выбрасывает соответствующие исключения.
        """
        try:
            logger.debug("Navigating to %s", url)
            response = await page.goto(url, wait_until=wait_until, timeout=30000)
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
            await page.wait_for_timeout(500)  # небольшая пауза для динамики
            html = await page.content()
            logger.debug("Page loaded, HTML length: %d", len(html))
            return html
        except Exception as e:
            logger.error("Navigation error to %s: %s", url, e, exc_info=True)
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
        await self._ensure_browser()
        parsed = urlparse(search_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        params = parse_qs(parsed.query)
        flat_params = {k: v[0] for k, v in params.items()}

        vacancies = []
        last_page = 0
        for page in range(max_pages):
            page_params = flat_params.copy()
            page_params["page"] = str(page)
            query = "&".join(f"{k}={v}" for k, v in page_params.items())
            url = f"{base_url}?{query}"

            # Создаём новую страницу для каждого запроса
            page_obj = await self._context.new_page()
            try:
                html = await self._goto(page_obj, url, wait_until="domcontentloaded")
                logger.info("Search page %d loaded, length=%d", page, len(html))

                if logger.isEnabledFor(logging.DEBUG):
                    with open(f"debug_search_page_{page}.html", "w", encoding="utf-8") as f:
                        f.write(html)

                # Пробуем извлечь вакансии через JSON (старый метод)
                try:
                    page_vacancies = extract_json_from_html(html, "vacancies")
                    logger.debug("Extracted %d vacancies via JSON", len(page_vacancies))
                except HHParseError:
                    logger.warning("Failed to extract vacancies via JSON, falling back to CSS selectors")
                    # Резервный парсинг через CSS-селекторы (с BeautifulSoup)
                    page_vacancies = await self._parse_vacancies_from_html(html)

                if not page_vacancies:
                    logger.info("No vacancies found on page %d", page)
                    break

                for raw in page_vacancies:
                    try:
                        vacancy = VacancyPreview.model_validate(raw)
                        vacancies.append(vacancy)
                    except Exception as e:
                        logger.warning("Failed to parse vacancy: %s", e, exc_info=True)
                last_page = page
            except HHError as e:
                logger.error("Failed to load search page %d: %s", page, e)
                break
            finally:
                await page_obj.close()
                logger.debug("Search page %d closed", page)

            # Задержка между страницами
            await asyncio.sleep(2)

        logger.info("Found %d vacancies across %d pages", len(vacancies), last_page + 1)
        return vacancies

    async def _parse_vacancies_from_html(self, html: str) -> List[Dict]:
        """
        Резервный метод парсинга вакансий через CSS-селекторы (если JSON не найден).
        Возвращает список словарей, совместимых с VacancyPreview.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.select('[data-qa="vacancy-serp__vacancy"]')
        vacancies = []
        for card in cards:
            title_elem = card.select_one('[data-qa="serp-item__title-text"]')
            title = title_elem.get_text(strip=True) if title_elem else "Без названия"
            link_elem = card.select_one('[data-qa="serp-item__title"]')
            link = link_elem.get('href') if link_elem else None
            if link and link.startswith("/"):
                link = "https://hh.ru" + link
            vacancy_id = None
            if link and "/vacancy/" in link:
                match = re.search(r'/vacancy/(\d+)', link)
                if match:
                    vacancy_id = int(match.group(1))
            vacancies.append({
                "vacancyId": vacancy_id,
                "name": title,
                "link": link,
                "userTestPresent": False,
                "@responseLetterRequired": False,
            })
        return vacancies

    async def get_vacancy_details(self, vacancy_id: int) -> VacancyDetails:
        """
        Получает детальную информацию о вакансии.
        """
        await self._ensure_browser()
        url = f"{self.BASE_URL}/vacancy/{vacancy_id}"
        page = await self._context.new_page()
        try:
            html = await self._goto(page, url, wait_until="domcontentloaded")
            description = extract_description(html)
            skills = extract_skills(html)
            return VacancyDetails(
                description=description,
                skills=skills,
                full_html=html
            )
        finally:
            await page.close()
            logger.debug("Details page closed for vacancy %d", vacancy_id)

    async def get_vacancy_tests(self, vacancy_id: int) -> Dict[str, Any]:
        """
        Получает данные о тесте для вакансии (если есть).
        """
        await self._ensure_browser()
        url = f"{self.BASE_URL}/applicant/vacancy_response?vacancyId={vacancy_id}&startedWithQuestion=false"
        page = await self._context.new_page()
        try:
            html = await self._goto(page, url, wait_until="networkidle")
            tests_data = extract_json_from_html(html, "vacancyTests")
            return tests_data.get(str(vacancy_id), {})
        finally:
            await page.close()
            logger.debug("Tests page closed for vacancy %d", vacancy_id)

    async def apply(self, vacancy_id: int, resume_hash: str, letter: str = "") -> ApplyResult:
        """
        Отправляет отклик на вакансию через браузер.
        """
        await self._ensure_browser()
        vacancy_url = f"{self.BASE_URL}/vacancy/{vacancy_id}"
        page = await self._context.new_page()
        try:
            await self._goto(page, vacancy_url, wait_until="networkidle")

            # Ищем кнопку отклика
            response_button = await page.query_selector('a[data-qa="vacancy-response-link"]')
            if not response_button:
                logger.error("Response button not found for vacancy %d", vacancy_id)
                raise HHParseError("Response button not found")

            await response_button.click()
            await page.wait_for_load_state("networkidle")

            # Если есть поле для сопроводительного письма, заполняем
            letter_field = await page.query_selector('textarea[data-qa="vacancy-response-letter"]')
            if letter_field and letter:
                await letter_field.fill(letter)

            # Ищем кнопку отправки
            submit_button = await page.query_selector('button[data-qa="vacancy-response-submit"]')
            if not submit_button:
                logger.error("Submit button not found for vacancy %d", vacancy_id)
                raise HHParseError("Submit button not found")

            await submit_button.click()
            await page.wait_for_load_state("networkidle")

            # Проверяем результат
            html = await page.content()
            if "Ваш отклик отправлен" in html or "success" in html:
                logger.info("Successfully applied to vacancy %d", vacancy_id)
                return ApplyResult(success=True)
            else:
                error_elem = await page.query_selector('div[data-qa="vacancy-response-error"]')
                error_text = await error_elem.text_content() if error_elem else "Unknown error"
                if "negotiations-limit-exceeded" in error_text:
                    logger.warning("Daily limit exceeded on hh.ru for vacancy %d", vacancy_id)
                    return ApplyResult(success=False, error=error_text, limit_exceeded=True)
                logger.error("Failed to apply to vacancy %d: %s", vacancy_id, error_text)
                return ApplyResult(success=False, error=error_text)
        finally:
            await page.close()
            logger.debug("Apply page closed for vacancy %d", vacancy_id)

    async def is_logged_in(self) -> bool:
        """
        Проверяет, валидны ли текущие cookies.
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            html = await self._goto(page, f"{self.BASE_URL}/applicant/resumes", wait_until="domcontentloaded")
            return 'latestResumeHash' in html
        except HHAuthError:
            return False
        except Exception:
            return False
        finally:
            await page.close()
            logger.debug("Login check page closed")

    async def login(self, username: str, password: str) -> Dict[str, str]:
        """
        Выполняет вход на hh.ru через браузер и возвращает новые cookies.
        """
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            await self._goto(page, f"{self.BASE_URL}/account/login", wait_until="networkidle")

            await page.fill('input[name="username"]', username)
            await page.fill('input[name="password"]', password)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle")

            if page.url == f"{self.BASE_URL}/":
                # Успех
                cookies = await self._context.cookies()
                cookie_dict = {c["name"]: c["value"] for c in cookies}
                logger.info("Login successful for user %s", username)
                return cookie_dict
            else:
                error_elem = await page.query_selector('.error, .alert')
                error_text = await error_elem.text_content() if error_elem else "Unknown error"
                logger.error("Login failed for user %s: %s", username, error_text)
                raise HHAuthError(f"Login failed: {error_text}")
        finally:
            await page.close()
            logger.debug("Login page closed")
