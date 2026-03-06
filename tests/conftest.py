import pytest
from unittest.mock import AsyncMock, MagicMock

from hh_client import HHClient


@pytest.fixture
def mock_hh_client():
    """Создаёт мок-объект HHClient с замоканными методами."""
    client = AsyncMock(spec=HHClient)
    client.search_vacancies = AsyncMock()
    client.get_vacancy_details = AsyncMock()
    client.apply = AsyncMock()
    client.is_logged_in = AsyncMock()
    client.login = AsyncMock()
    return client


@pytest.fixture
def sample_vacancy_preview():
    """Возвращает пример данных VacancyPreview."""
    from hh_client.models import VacancyPreview, Salary
    return VacancyPreview(
        id=123456,
        title="Python Developer",
        url="https://hh.ru/vacancy/123456",
        has_test=False,
        response_letter_required=False,
        salary=Salary(from_=100000, to=150000, currency="RUR")
    )


@pytest.fixture
def sample_vacancy_details():
    """Возвращает пример данных VacancyDetails."""
    from hh_client.models import VacancyDetails
    return VacancyDetails(
        description="Требуется Python разработчик. Опыт работы от 1 года.",
        skills=["Python", "Django", "PostgreSQL"],
        full_html="<html>...</html>"
    )