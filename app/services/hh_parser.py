import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from playwright.async_api import async_playwright
from app.utils.proxy_rotator import get_proxy_for_account
from app.config import settings
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


class HHParser:
    def __init__(self, account_id: int, proxy: Optional[Dict] = None):
        self.account_id = account_id
        self.proxy = proxy or get_proxy_for_account(account_id)

    # async def search_vacancies(self, search_url: str, max_pages: int = 1) -> List[Dict]:
    #     vacancies = []
    #     async with async_playwright() as p:
    #         # ... запуск браузера
    #         for page_num in range(max_pages):
    #             # Добавляем параметр page к URL
    #             parsed = urlparse(search_url)
    #             query = parse_qs(parsed.query)
    #             query['page'] = [str(page_num)]
    #             new_query = urlencode(query, doseq=True)
    #             url = urlunparse(parsed._replace(query=new_query))
    #             await page.goto(url, ...)

    async def search_vacancies(self, search_url: str, max_pages: int = 1) -> List[Dict]:
        """
        Собирает базовую информацию о вакансиях со страниц поиска.
        Возвращает список: [{'id': str, 'title': str, 'link': str}, ...]
        """
        vacancies = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                proxy=self.proxy
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            for page_num in range(max_pages):
                url = f"{search_url}&page={page_num}" if "?" in search_url else f"{search_url}?page={page_num}"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_selector('[data-qa="vacancy-serp__vacancy"]', timeout=10000)
                except:
                    break

                await asyncio.sleep(2)
                cards = page.locator('[data-qa="vacancy-serp__vacancy"]')
                count = await cards.count()
                for i in range(count):
                    card = cards.nth(i)
                    title_elem = card.locator('[data-qa="serp-item__title-text"]')
                    title = await title_elem.text_content() or "Без названия"
                    link_elem = card.locator('[data-qa="serp-item__title"]')
                    link = await link_elem.get_attribute('href')
                    if link and link.startswith("/"):
                        link = "https://hh.ru" + link
                    vacancy_id = None
                    if link and "/vacancy/" in link:
                        vacancy_id = link.split("/vacancy/")[-1].split("?")[0]
                    vacancies.append({
                        "id": vacancy_id,
                        "title": title.strip(),
                        "link": link
                    })
                await asyncio.sleep(3)
            await browser.close()
        return vacancies

    async def parse_vacancy_details(self, vacancy_url: str) -> Dict:
        """
        Загружает страницу вакансии и извлекает описание и требуемый опыт.
        Возвращает словарь с полями description, experience.
        """
        details = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, proxy=self.proxy)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            try:
                await page.goto(vacancy_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_selector('[data-qa="vacancy-description"]', timeout=10000)
                await asyncio.sleep(1)
                desc_elem = page.locator('[data-qa="vacancy-description"]')
                description = await desc_elem.text_content() if await desc_elem.count() > 0 else ""
                details["description"] = description.strip() if description else ""
                exp_elem = page.locator('[data-qa="vacancy-experience"]')
                experience = await exp_elem.text_content() if await exp_elem.count() > 0 else None
                details["experience"] = experience.strip() if experience else None
            except Exception as e:
                details = {"error": str(e), "description": "", "experience": None}
            finally:
                await browser.close()
        return details

    async def fetch_invitations(self) -> List[Dict]:
        """
        Парсит страницу откликов/приглашений и возвращает список новых приглашений.
        Каждый элемент: {
            'vacancy_hh_id': str,
            'vacancy_title': str,
            'company': str,
            'invited_at': datetime,
            'message': str (текст приглашения, если есть)
        }
        """
        invitations = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, proxy=self.proxy)
            context = await browser.new_context()
            page = await context.new_page()

            # Авторизация (если нужна) — можно передавать cookies из БД
            # Здесь предполагаем, что сессия уже активна (cookies сохранены в Account.cookies)

            # Переходим на страницу приглашений (обычно https://hh.ru/applicant/invites)
            await page.goto("https://hh.ru/applicant/invites", wait_until="domcontentloaded")
            await page.wait_for_selector('[data-qa="invite-item"]', timeout=10000)

            # Собираем все приглашения
            items = page.locator('[data-qa="invite-item"]')
            count = await items.count()
            for i in range(count):
                item = items.nth(i)

                # Заголовок вакансии и ссылка
                title_elem = item.locator('[data-qa="invite-item__vacancy-title"]')
                title = await title_elem.text_content()
                link = await title_elem.get_attribute('href')
                vacancy_hh_id = None
                if link and "/vacancy/" in link:
                    vacancy_hh_id = link.split("/vacancy/")[-1].split("?")[0]

                # Компания
                company_elem = item.locator('[data-qa="invite-item__company-name"]')
                company = await company_elem.text_content()

                # Дата приглашения
                date_elem = item.locator('[data-qa="invite-item__date"]')
                date_text = await date_elem.text_content()
                # Преобразование текста в datetime (например, "сегодня", "вчера", "23 марта 2025")
                invited_at = self._parse_invite_date(date_text)

                # Сообщение (если есть)
                msg_elem = item.locator('[data-qa="invite-item__message"]')
                message = await msg_elem.text_content() if await msg_elem.count() > 0 else None

                invitations.append({
                    "vacancy_hh_id": vacancy_hh_id,
                    "vacancy_title": title.strip(),
                    "company": company.strip(),
                    "invited_at": invited_at,
                    "message": message.strip() if message else None
                })

            await browser.close()
        return invitations

    def _parse_invite_date(self, date_text: str) -> datetime:
        """Преобразует относительную дату в datetime."""
        # Упрощённая реализация — на основе текущей даты
        # В реальном проекте лучше использовать парсинг с учётом временной зоны
        now = datetime.now()
        if "сегодня" in date_text.lower():
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif "вчера" in date_text.lower():
            return (now - datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Попытка распарсить "23 марта 2025"
            try:
                return datetime.strptime(date_text.strip(), "%d %B %Y")
            except:
                return now
