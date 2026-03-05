# hh_client/client.py
"""Основной асинхронный клиент для работы с hh.ru."""

import asyncio
import json
import logging
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs

import aiohttp

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
    """Асинхронный клиент для hh.ru."""

    BASE_URL = "https://hh.ru"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    }

    def __init__(self, cookies: Dict[str, str], proxy: Optional[str] = None):
        """
        :param cookies: Словарь cookies (например, полученные после логина).
        :param proxy: Прокси в формате "http://user:pass@host:port".
        """
        self._cookies = cookies
        self._proxy = proxy
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        await self._create_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _create_session(self):
        """Создаёт aiohttp сессию и устанавливает cookies и прокси."""
        self._session = aiohttp.ClientSession(headers=self.HEADERS)
        # Устанавливаем cookies
        for name, value in self._cookies.items():
            self._session.cookie_jar.update_cookies({name: value})
        # Прокси (aiohttp поддерживает прокси на уровне запроса, а не сессии)
        # Мы будем передавать proxy в каждый запрос
        logger.debug("HHClient session created with cookies: %s", list(self._cookies.keys()))

    async def close(self):
        """Закрывает сессию."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("HHClient session closed")

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> str:
        """
        Выполняет HTTP-запрос и возвращает текст ответа.
        При ошибках выбрасывает соответствующие исключения.
        """
        if not self._session or self._session.closed:
            await self._create_session()

        url = self.BASE_URL + path
        request_headers = self.HEADERS.copy()
        if headers:
            request_headers.update(headers)

        try:
            logger.debug("Request: %s %s, params=%s", method, url, params)
            async with self._session.request(
                method,
                url,
                params=params,
                data=data,
                headers=request_headers,
                proxy=self._proxy,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                logger.debug("Response status: %d for %s", resp.status, url)
                if resp.status == 401:
                    raise HHAuthError("Unauthorized (cookies may be expired)")
                if resp.status == 403:
                    raise HHAuthError("Access forbidden")
                if resp.status == 429:
                    raise HHRateLimitError("Rate limit exceeded")
                resp.raise_for_status()
                return await resp.text()
        except asyncio.TimeoutError as e:
            raise HHNetworkError(f"Request timeout: {e}")
        except aiohttp.ClientError as e:
            raise HHNetworkError(f"Network error: {e}")

    @property
    def xsrf_token(self) -> Optional[str]:
        """Возвращает значение cookie _xsrf, если есть."""
        if self._session:
            for cookie in self._session.cookie_jar:
                if cookie.key == "_xsrf":
                    return cookie.value
        return None

    # === Публичные методы ===

    async def search_vacancies(self, search_url: str, max_pages: int = 1) -> List[VacancyPreview]:
        """
        Ищет вакансии по заданному URL поиска.
        Возвращает список VacancyPreview.
        """
        parsed = urlparse(search_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        params = parse_qs(parsed.query)
        # Преобразуем значения из списков в строки (aiohttp может принимать списки, но для безопасности)
        params = {k: v[0] if v else "" for k, v in params.items()}

        vacancies = []
        last_page = 0
        for page in range(max_pages):
            page_params = params.copy()
            page_params["page"] = str(page)
            html = await self._request("GET", base_url, params=page_params)
            try:
                page_vacancies = extract_json_from_html(html, "vacancies")
            except HHParseError:
                logger.debug("No more vacancies at page %d", page)
                break
            for raw in page_vacancies:
                try:
                    vacancy = VacancyPreview.model_validate(raw)
                    vacancies.append(vacancy)
                except Exception as e:
                    logger.warning("Failed to parse vacancy: %s", e, exc_info=True)
            last_page = page
            await asyncio.sleep(2)

        logger.info("Found %d vacancies across %d pages", len(vacancies), last_page + 1)

        return vacancies

    async def get_vacancy_details(self, vacancy_id: int) -> VacancyDetails:
        """
        Получает детальную информацию о вакансии.
        """
        html = await self._request("GET", f"/vacancy/{vacancy_id}")
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
        url = f"/applicant/vacancy_response?vacancyId={vacancy_id}&startedWithQuestion=false"
        html = await self._request("GET", url)
        tests_data = extract_json_from_html(html, "vacancyTests")
        return tests_data.get(str(vacancy_id), {})

    async def apply(
        self,
        vacancy_id: int,
        resume_hash: str,
        letter: str = "",
    ) -> ApplyResult:
        """
        Отправляет отклик на вакансию.
        Автоматически определяет наличие теста и формирует соответствующий payload.
        """
        # Проверяем, есть ли тест
        try:
            tests = await self.get_vacancy_tests(vacancy_id)
            has_test = bool(tests)
        except Exception as e:
            logger.warning("Failed to get tests for vacancy %d: %s", vacancy_id, e)
            has_test = False

        if has_test:
            # Формируем payload для теста (адаптация из кода друга)
            payload = {
                "_xsrf": self.xsrf_token,
                "vacancy_id": vacancy_id,
                "resume_hash": resume_hash,
                "letter": letter,
                "ignore_postponed": "true",
                "uidPk": tests.get("uidPk"),
                "guid": tests.get("guid"),
                "startTime": tests.get("startTime"),
                "testRequired": tests.get("required", False),
                "incomplete": "false",
                "lux": "true",
                "withoutTest": "no",
            }
            # Добавляем ответы на задачи
            for task in tests.get("tasks", []):
                task_id = task["id"]
                solutions = task.get("candidateSolutions", [])
                if solutions:
                    # Берём вариант из середины
                    answer_id = solutions[len(solutions) // 2]["id"]
                    payload[f"task_{task_id}"] = answer_id
                else:
                    # Если нет вариантов, ставим "Да"
                    payload[f"task_{task_id}_text"] = "Да"

            referer = self.BASE_URL + f"/vacancy/{vacancy_id}"
            result_data = await self._send_response(payload, referer)
        else:
            # Простой отклик
            payload = {
                "_xsrf": self.xsrf_token,
                "vacancy_id": vacancy_id,
                "resume_hash": resume_hash,
                "letter": letter,
                "ignore_postponed": "true",
            }
            referer = self.BASE_URL + f"/vacancy/{vacancy_id}"
            result_data = await self._send_response(payload, referer)

        # Анализ результата
        if result_data.get("success"):
            return ApplyResult(success=True)
        else:
            error = result_data.get("error", "Unknown error")
            if error == "negotiations-limit-exceeded":
                return ApplyResult(success=False, error=error, limit_exceeded=True)
            return ApplyResult(success=False, error=error)

    async def _send_response(self, payload: Dict, referer: str) -> Dict:
        """Внутренний метод для отправки POST-запроса на отклик."""
        headers = {
            "X-Hhtmfrom": "vacancy",
            "X-Hhtmsource": "vacancy_response",
            "X-Requested-With": "XMLHttpRequest",
            "X-Xsrftoken": self.xsrf_token,
            "Referer": referer,
        }
        # Преобразуем payload в формат application/x-www-form-urlencoded
        data = aiohttp.FormData()
        for key, value in payload.items():
            if value is not None:
                data.add_field(key, str(value))

        html = await self._request("POST", "/applicant/vacancy_response/popup", data=data, headers=headers)
        try:
            return json.loads(html)
        except json.JSONDecodeError as e:
            raise HHParseError(f"Failed to parse response JSON: {e}")

    async def is_logged_in(self) -> bool:
        """Проверяет, валидны ли текущие cookies."""
        try:
            html = await self._request("GET", "/applicant/resumes")
            return 'latestResumeHash' in html
        except HHAuthError:
            return False
        except Exception:
            return False

    async def login(self, username: str, password: str) -> Dict[str, str]:
        """
        Выполняет вход и возвращает новые cookies.
        ВНИМАНИЕ: этот метод создаёт новую сессию, не использует текущую.
        После получения cookies можно создать новый экземпляр HHClient.
        """
        # Для логина используем отдельную сессию без cookies
        async with aiohttp.ClientSession() as session:
            session.headers.update(self.HEADERS)
            # 1. Получаем страницу логина для извлечения _xsrf
            resp = await session.get("https://hh.ru/account/login", proxy=self._proxy)
            html = await resp.text()
            xsrf_match = re.search(r'name="_xsrf" value="([^"]+)"', html)
            if not xsrf_match:
                raise HHAuthError("Could not extract _xsrf token")
            xsrf = xsrf_match.group(1)

            # 2. Отправляем POST с логином/паролем
            login_data = {
                "_xsrf": xsrf,
                "backUrl": "https://hh.ru/",
                "username": username,
                "password": password,
                "action": "Войти",
            }
            resp = await session.post(
                "https://hh.ru/account/login",
                data=login_data,
                allow_redirects=False,
                proxy=self._proxy,
            )
            if resp.status == 302 and resp.headers.get("Location") == "https://hh.ru/":
                # Успех
                cookies = {}
                for cookie in session.cookie_jar:
                    cookies[cookie.key] = cookie.value
                return cookies
            else:
                # Пытаемся прочитать ошибку
                text = await resp.text()
                logger.error("Login failed: status %d, body %s", resp.status, text[:200])
                raise HHAuthError("Login failed")
