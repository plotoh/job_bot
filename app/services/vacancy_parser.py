import logging
from typing import List, Dict, Optional

from app.services.hh_api import HHApiClient
from app.utils.proxy_rotator import get_proxy_for_account

logger = logging.getLogger(__name__)


class HHSearcher:
    """Поиск вакансий через HTTP-клиент."""

    def __init__(self, account_id: int, cookies: Dict[str, str], resume_hash: str, proxy: Optional[Dict] = None):
        self.account_id = account_id
        self.client = HHApiClient(account_id, cookies, resume_hash, proxy)

    async def search(self, search_url: str, max_pages: int = 1) -> List[Dict]:
        """Возвращает список вакансий (минимальные данные)."""
        return self.client.search_vacancies(search_url, max_pages)


class HHDetailParser:
    """Получение деталей вакансии."""

    def __init__(self, cookies: Dict[str, str], proxy: Optional[Dict] = None):
        # Для деталей можно использовать временный клиент без аккаунта (но с cookies)
        self.client = HHApiClient(0, cookies, "", proxy)  # resume_hash не нужен для деталей

    async def parse(self, vacancy_id: int) -> Dict:
        """Возвращает детали вакансии."""
        return self.client.get_vacancy_details(vacancy_id)
