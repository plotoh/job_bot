import json
import logging
import random
import re
import time
from typing import Optional, Dict, List, Any, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.utils.encryption import decrypt_password
from app.config import settings

logger = logging.getLogger(__name__)


class HHApiClient:
    """Клиент для взаимодействия с hh.ru через HTTP-запросы (без браузера)."""

    BASE_URL = "https://hh.ru"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ACCEPT_LANGUAGE = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"

    def __init__(self, account_id: int, cookies: Dict[str, str], resume_hash: str, proxy: Optional[str] = None):
        self.account_id = account_id
        self.resume_hash = resume_hash
        self.proxy = proxy

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept-Language": self.ACCEPT_LANGUAGE,
        })

        # Устанавливаем cookies
        requests.utils.add_dict_to_cookiejar(self.session.cookies, cookies)

        # Настройка повторных попыток
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # Прокси
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})

    @property
    def xsrf_token(self) -> Optional[str]:
        return self.session.cookies.get("_xsrf")

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Выполняет HTTP-запрос с обработкой ошибок."""
        url = urljoin(self.BASE_URL, path)
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            raise

    def _extract_json_from_html(self, text: str, key: str) -> Any:
        """
        Извлекает JSON-объект из HTML по ключу.
        Пример: ,"vacancies":[{...}]
        """
        # Ищем ключ: ,"key": (за которым идёт JSON)
        pattern = rf',"{key}":(.+?)(?=,\s*"|\]|\Z)'
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            raise ValueError(f"Key '{key}' not found in HTML")
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON for key {key}: {e}")
            raise

    def _extract_description(self, html: str) -> str:
        """Извлекает текст описания вакансии из HTML (по data-qa='vacancy-description')."""
        # Простой способ: найти div с атрибутом data-qa="vacancy-description" и взять его текст
        pattern = r'<div[^>]*data-qa="vacancy-description"[^>]*>(.*?)</div>'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            # Удалить HTML-теги, оставить текст
            text = re.sub(r'<[^>]+>', '', match.group(1))
            # Заменить множественные пробелы/переносы
            text = re.sub(r'\s+', ' ', text).strip()
            return text
        return ""

    def _extract_salary(self, vacancy_data: Dict) -> Dict:
        """Извлекает зарплату из данных вакансии (из JSON в списке)."""
        salary = vacancy_data.get("salary")
        if salary and isinstance(salary, dict):
            return {
                "from": salary.get("from"),
                "to": salary.get("to"),
                "currency": salary.get("currency"),
                "gross": salary.get("gross", False)
            }
        return {}

    # ===== Публичные методы =====

    def is_logged_in(self) -> bool:
        """Проверяет, валидны ли cookies (делает запрос к странице профиля)."""
        try:
            resp = self._request("GET", "/applicant/resumes")
            # Если страница содержит данные резюме, считаем, что авторизация есть
            return 'latestResumeHash' in resp.text
        except:
            return False

    def search_vacancies(self, search_url: str, max_pages: int = 1) -> List[Dict]:
        """
        Ищет вакансии по заданному URL и возвращает список с минимальными данными.
        Каждый элемент содержит: id, title, link, salary (опционально), и др.
        """
        parsed = urlparse(search_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        params = parse_qs(parsed.query)

        vacancies = []
        for page in range(max_pages):
            params["page"] = [str(page)]
            resp = self._request("GET", base_url, params=params)
            try:
                page_vacancies = self._extract_json_from_html(resp.text, "vacancies")
            except ValueError:
                # Если ключ не найден, значит страниц больше нет
                break

            for vac in page_vacancies:
                # Основные поля
                item = {
                    "id": vac["vacancyId"],
                    "title": vac.get("name", "Без названия"),
                    "link": vac.get("links", {}).get("desktop"),
                    "employment": vac.get("employment"),
                    "work_experience": vac.get("workExperience"),
                    "work_formats": vac.get("workFormats", []),
                    "salary": self._extract_salary(vac),
                    "response_letter_required": vac.get("@responseLetterRequired", False),
                    "has_test": vac.get("userTestPresent", False),
                }
                vacancies.append(item)

            # Задержка между страницами
            time.sleep(random.uniform(2, 4))

        return vacancies

    def get_vacancy_details(self, vacancy_id: int) -> Dict:
        """
        Получает детальную информацию о вакансии (описание и пр.).
        """
        url = f"/vacancy/{vacancy_id}"
        resp = self._request("GET", url)
        description = self._extract_description(resp.text)

        # Можно также извлечь ключевые навыки, если есть
        # (опционально, через data-qa="vacancy-key-skills")
        skills = []
        skills_pattern = r'<span[^>]*data-qa="vacancy-key-skills"[^>]*>(.*?)</span>'
        for match in re.finditer(skills_pattern, resp.text, re.DOTALL):
            skill_text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if skill_text:
                skills.append(skill_text)

        return {
            "description": description,
            "skills": skills,
            "full_html": resp.text  # если нужно для дальнейшего парсинга
        }

    def get_vacancy_tests(self, vacancy_id: int) -> Dict:
        """
        Получает данные о тесте для вакансии (если есть).
        Возвращает словарь с полями uidPk, guid, startTime, tasks и т.д.
        """
        url = f"/applicant/vacancy_response?vacancyId={vacancy_id}&startedWithQuestion=false"
        resp = self._request("GET", url)
        tests_data = self._extract_json_from_html(resp.text, "vacancyTests")
        return tests_data.get(str(vacancy_id), {})

    def send_response(self, payload: Dict, referer: str) -> Dict:
        """
        Отправляет POST-запрос на отклик.
        Возвращает JSON-ответ от сервера.
        """
        headers = {
            "X-Hhtmfrom": "vacancy",
            "X-Hhtmsource": "vacancy_response",
            "X-Requested-With": "XMLHttpRequest",
            "X-Xsrftoken": self.xsrf_token,
            "Referer": referer,
        }
        resp = self._request("POST", "/applicant/vacancy_response/popup", data=payload, headers=headers)
        return resp.json()

    def apply(self, vacancy_id: int, vacancy_url: str, letter: str = "") -> Tuple[bool, Optional[str]]:
        """
        Отправляет отклик на вакансию.
        Возвращает (успех, сообщение об ошибке или None).
        """
        # Проверяем, есть ли тест
        try:
            tests = self.get_vacancy_tests(vacancy_id)
            has_test = bool(tests)
        except Exception as e:
            logger.warning(f"Failed to get tests for vacancy {vacancy_id}: {e}")
            has_test = False

        if has_test:
            # Формируем payload для теста (логика из скрипта друга)
            payload = {
                "_xsrf": self.xsrf_token,
                "vacancy_id": vacancy_id,
                "resume_hash": self.resume_hash,
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
                    # Берём вариант из середины (как в скрипте)
                    answer_id = solutions[len(solutions) // 2]["id"]
                    payload[f"task_{task_id}"] = answer_id
                else:
                    # Если нет вариантов, ставим "Да" (в текстовое поле)
                    payload[f"task_{task_id}_text"] = "Да"

            result = self.send_response(payload, vacancy_url)
        else:
            # Простой отклик без теста
            payload = {
                "_xsrf": self.xsrf_token,
                "vacancy_id": vacancy_id,
                "resume_hash": self.resume_hash,
                "letter": letter,
                "ignore_postponed": "true",
            }
            result = self.send_response(payload, vacancy_url)

        # Анализ результата
        if result.get("success"):
            return True, None
        else:
            error = result.get("error", "Unknown error")
            if error == "negotiations-limit-exceeded":
                logger.info("Daily response limit exceeded on hh.ru side.")
            return False, error
