import asyncio
import logging
from typing import List, Dict, Optional
from playwright.async_api import async_playwright
from app.utils.proxy_rotator import get_proxy_for_account

logger = logging.getLogger(__name__)


class HHSearcher:
    def __init__(self, account_id: int, proxy: Optional[Dict] = None):
        self.account_id = account_id
        self.proxy = proxy or get_proxy_for_account(account_id)

    async def search(self, search_url: str, max_pages: int = 1) -> List[Dict]:
        vacancies = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, proxy=self.proxy)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
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


class HHDetailParser:
    def __init__(self, proxy: Optional[Dict] = None):
        self.proxy = proxy

    async def parse(self, vacancy_url: str) -> Dict:
        details = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, proxy=self.proxy)
            context = await browser.new_context(user_agent="...")
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
                logger.error(f"Ошибка парсинга {vacancy_url}: {e}")
                details = {"error": str(e), "description": "", "experience": None}
            finally:
                await browser.close()
        return details
