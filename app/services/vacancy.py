# app/services/vacancy.py
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import Account, Vacancy, AccountVacancy
from app.services.vacancy_filter import is_backend_python_keywords, extract_secret_word
from hh_client import HHClient, VacancyPreview, VacancyDetails

logger = logging.getLogger(__name__)


async def matches_criteria(
        vacancy_preview: VacancyPreview,
        details: Optional[VacancyDetails],
        account: Account,
) -> bool:
    """
    Проверяет, подходит ли вакансия для данного аккаунта на основе его фильтра.
    """
    # Если в фильтре отключена проверка по ключевым словам, считаем что подходит
    if not account.search_filter.get("use_keyword_filter", True):
        return True

    # Базовая проверка на backend Python
    title = vacancy_preview.title
    description = details.description if details else ""
    if not is_backend_python_keywords(title, description):
        logger.debug("Vacancy %s (%s) does not match backend Python keywords", vacancy_preview.id, title)
        return False

    # Дополнительные ключевые слова из фильтра
    keywords = account.search_filter.get("keywords", [])
    if keywords:
        text = (title + " " + description).lower()
        if not any(kw.lower() in text for kw in keywords):
            logger.debug("Vacancy %s missing required keywords: %s", vacancy_preview.id, keywords)
            return False

    exclude_keywords = account.search_filter.get("exclude_keywords", [])
    if exclude_keywords:
        text = (title + " " + description).lower()
        if any(kw.lower() in text for kw in exclude_keywords):
            logger.debug("Vacancy %s contains excluded keywords: %s", vacancy_preview.id, exclude_keywords)
            return False

    # Здесь можно добавить другие проверки (зарплата, опыт и т.д.)
    return True


async def fetch_and_save_new_vacancies(account: Account, session: AsyncSession) -> int:
    """
    Ищет новые вакансии по фильтру аккаунта, проверяет критерии и сохраняет в БД.
    Возвращает количество сохранённых вакансий.
    """
    search_filter = account.search_filter or {}
    search_url = search_filter.get("url")
    if not search_url:
        logger.warning("Account %d has no search URL", account.id)
        return 0

    try:
        async with HHClient(account.cookies or {}, account.proxy) as client:
            if not await client.is_logged_in():
                logger.warning("Account %d cookies are invalid, skipping", account.id)
                return 0
            logger.info("Account %d cookies are valid", account.id)
            vacancies_preview = await client.search_vacancies(search_url, account.max_pages)
    except Exception as e:
        logger.error("Error searching vacancies for account %d: %s", account.id, e, exc_info=True)
        return 0

    saved_count = 0
    for preview in vacancies_preview:
        existing = await session.execute(
            select(Vacancy).where(Vacancy.hh_id == str(preview.id))
        )
        vacancy = existing.scalar_one_or_none()
        if vacancy:
            # Связь с аккаунтом может отсутствовать
            await _ensure_account_vacancy_link(account, vacancy, session)
            continue

        try:
            details = await client.get_vacancy_details(preview.id)
        except Exception as e:
            logger.error("Failed to get details for vacancy %d: %s", preview.id, e, exc_info=True)
            continue

        if not await matches_criteria(preview, details, account):
            continue

        secret = extract_secret_word(details.description)

        vacancy = Vacancy(
            hh_id=str(preview.id),
            title=preview.title,
            url=preview.url,
            description=details.description,
            check_word=secret,
        )
        session.add(vacancy)
        await session.flush()

        account_vacancy = AccountVacancy(
            account_id=account.id,
            vacancy_id=vacancy.id,
            viewed_at=datetime.utcnow(),
            responded=False,
        )
        session.add(account_vacancy)
        saved_count += 1
        logger.info("Saved new vacancy %d: %s", preview.id, preview.title)

    await session.commit()
    return saved_count


async def _ensure_account_vacancy_link(account: Account, vacancy: Vacancy, session: AsyncSession):
    existing = await session.execute(
        select(AccountVacancy).where(
            AccountVacancy.account_id == account.id,
            AccountVacancy.vacancy_id == vacancy.id
        )
    )
    if not existing.scalar_one_or_none():
        account_vacancy = AccountVacancy(
            account_id=account.id,
            vacancy_id=vacancy.id,
            viewed_at=datetime.utcnow(),
            responded=False,
        )
        session.add(account_vacancy)
        await session.commit()
        logger.debug("Created account_vacancy link for account %d, vacancy %d", account.id, vacancy.id)
