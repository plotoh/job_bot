#!/usr/bin/env python
"""
Локальный тест парсинга вакансий с hh.ru через hh_client.
Использует cookies из файла и URL фильтра.
"""
import asyncio
import logging
import os
import sys
import http.cookiejar
from pathlib import Path

from hh_client import HHClient
from hh_client.exceptions import HHError


# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))


# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    # --- НАСТРОЙКИ (измените при необходимости) ---
    COOKIES_FILE = Path(__file__).parent.parent / "hh.ru_cookies.txt"  # ваш файл
    SEARCH_URL = (
        "https://hh.ru/search/vacancy?text=Python+Developer&area=1"
        "&employment_form=FULL&work_format=REMOTE&order_by=relevance"
        "&items_on_page=50"
    )
    MAX_PAGES = 2
    PROXY = None  # или "http://user:pass@host:port"

    # Проверяем наличие файла cookies
    if not COOKIES_FILE.exists():
        logger.error("Файл %s не найден", COOKIES_FILE)
        return

    # Загружаем cookies из файла (формат Netscape)
    jar = http.cookiejar.MozillaCookieJar(str(COOKIES_FILE))
    jar.load(ignore_discard=True, ignore_expires=True)
    cookies = {cookie.name: cookie.value for cookie in jar}
    logger.info("Загружено cookies: %s", list(cookies.keys()))

    # Создаём клиент и выполняем поиск
    async with HHClient(cookies, proxy=PROXY) as client:
        # Проверяем авторизацию
        if await client.is_logged_in():
            logger.info("✅ Cookies валидны, авторизация успешна")
        else:
            logger.warning("⚠️ Cookies недействительны")

        # Выполняем поиск
        try:
            logger.info("Запуск поиска по URL: %s", SEARCH_URL)
            vacancies = await client.search_vacancies(SEARCH_URL, max_pages=MAX_PAGES)
            logger.info("✅ Найдено вакансий: %d", len(vacancies))
            for i, v in enumerate(vacancies[:5], 1):
                logger.info("  %d. %s (ID: %s)", i, v.title, v.id)

            # Если вакансий нет, возможно, стоит сохранить HTML для анализа
            if not vacancies:
                logger.info("Попытка получить HTML для анализа...")
                # Можно напрямую вызвать _request для отладки, но лучше модифицировать клиент
        except HHError as e:
            logger.error("Ошибка при поиске: %s", e)
            # Дополнительно можно сохранить последний ответ, если есть доступ к html
            # Для этого потребуется модифицировать клиент (см. примечание ниже)


if __name__ == "__main__":
    asyncio.run(main())
