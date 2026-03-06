import pytest
from unittest.mock import Mock
from app.services.vacancy import matches_criteria
from app.database.models import Account
from hh_client.models import VacancyPreview, VacancyDetails


@pytest.mark.asyncio
async def test_matches_criteria_keywords():
    account = Account(search_filter={
        "use_keyword_filter": True,
        "keywords": ["django"],
        "exclude_keywords": ["банан"]
    })
    preview = VacancyPreview(
        id=1,
        title="Python Developer",
        url="",
        has_test=False,
        response_letter_required=False
    )
    details = VacancyDetails(
        description="Требуется Django разработчик. Не senior."
    )

    assert await matches_criteria(preview, details, account) is True


@pytest.mark.asyncio
async def test_matches_criteria_exclude():
    account = Account(search_filter={
        "use_keyword_filter": True,
        "keywords": [],
        "exclude_keywords": ["senior"]
    })
    preview = VacancyPreview(
        id=1,
        title="Senior Python Developer",
        url="",
        has_test=False,
        response_letter_required=False
    )
    details = VacancyDetails(description="")

    assert await matches_criteria(preview, details, account) is False


@pytest.mark.asyncio
async def test_matches_criteria_no_filter():
    account = Account(search_filter={"use_keyword_filter": False})
    preview = Mock(spec=VacancyPreview)
    details = Mock(spec=VacancyDetails)
    assert await matches_criteria(preview, details, account) is True
