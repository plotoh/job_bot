# app/services/response.py
import asyncio
import logging
import random
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models import Account, Vacancy, Response, AccountVacancy, DailyStats
from app.services.letter_generator import generate_cover_letter
from hh_client import HHClient, ApplyResult

logger = logging.getLogger(__name__)


async def _update_daily_stats(account_id: int, session: AsyncSession, increment_responses: bool = True,
                              increment_invitations: bool = False):
    """Обновляет статистику дня для аккаунта."""
    today = date.today()
    stmt = select(DailyStats).where(
        and_(
            DailyStats.account_id == account_id,
            DailyStats.date == today
        )
    )
    result = await session.execute(stmt)
    stats = result.scalar_one_or_none()

    if stats is None:
        stats = DailyStats(
            account_id=account_id,
            date=today,
            responses_count=1 if increment_responses else 0,
            invitations_count=1 if increment_invitations else 0
        )
        session.add(stats)
    else:
        if increment_responses:
            stats.responses_count += 1
        if increment_invitations:
            stats.invitations_count += 1
    await session.flush()


async def send_response_for_vacancy(
        account: Account,
        vacancy: Vacancy,
        session: AsyncSession,
        test_mode: bool = False,
) -> bool:
    """
    Генерирует письмо и отправляет отклик на вакансию.
    В test_mode не отправляет реально, а только генерирует письмо и возвращает True.
    """
    try:
        letter = await generate_cover_letter(account, vacancy, vacancy.check_word)
    except Exception as e:
        logger.error("Failed to generate letter for vacancy %d: %s", vacancy.id, e, exc_info=True)
        return False

    if test_mode:
        logger.debug("Test mode: letter generated for vacancy %d", vacancy.id)
        return True

    response = Response(
        account_id=account.id,
        vacancy_id=vacancy.id,
        cover_letter=letter,
        status="pending",
    )
    session.add(response)
    await session.flush()

    stmt = select(AccountVacancy).where(
        AccountVacancy.account_id == account.id,
        AccountVacancy.vacancy_id == vacancy.id
    )
    av = (await session.execute(stmt)).scalar_one_or_none()
    if av:
        av.responded = True
        av.response_id = response.id
    else:
        av = AccountVacancy(
            account_id=account.id,
            vacancy_id=vacancy.id,
            viewed_at=datetime.utcnow(),
            responded=True,
            response_id=response.id,
        )
        session.add(av)

    try:
        async with HHClient(account.cookies or {}, account.proxy) as client:
            result = await client.apply(int(vacancy.hh_id), account.resume_id, letter)
    except Exception as e:
        logger.error("Error sending response for vacancy %d: %s", vacancy.id, e, exc_info=True)
        response.status = "error"
        response.error_message = str(e)
        await session.commit()
        return False

    if result.success:
        response.status = "sent"
        response.sent_at = datetime.utcnow()
        account.responses_today += 1
        # Обновляем дневную статистику
        await _update_daily_stats(account.id, session, increment_responses=True)
        logger.info("Response %d sent successfully for vacancy %d", response.id, vacancy.id)
        await session.commit()
        return True

    else:
        response.status = "error"
        response.error_message = result.error
        if result.limit_exceeded:
            logger.warning("Daily limit exceeded on hh.ru for account %d", account.id)
        else:
            logger.error("Failed to send response: %s", result.error)
        await session.commit()
        return False


def is_working_hours(account: Account) -> bool:
    """Проверяет, сейчас рабочее время для аккаунта (по Москве)."""
    from datetime import datetime
    import pytz
    msk_tz = pytz.timezone('Europe/Moscow')
    now_msk = datetime.now(msk_tz)
    hour = now_msk.hour
    return account.work_start_hour <= hour < account.work_end_hour


async def process_pending_responses(
        account: Account,
        session: AsyncSession,
        test_mode: bool = False,
) -> List[dict]:
    """
    Обрабатывает ожидающие отклики для аккаунта.
    Возвращает список отчётов по каждой попытке.
    """
    from app.services.account_crud import reset_daily_limit_if_needed

    await reset_daily_limit_if_needed(account, session)

    if not test_mode and not is_working_hours(account):
        logger.debug("Account %d is outside working hours, skipping", account.id)
        return []

    remaining = account.daily_response_limit - account.responses_today
    if remaining <= 0 and not test_mode:
        logger.info("Account %d reached daily limit (%d/%d)", account.id, account.responses_today,
                    account.daily_response_limit)
        return []

    subq = select(AccountVacancy.vacancy_id).where(
        AccountVacancy.account_id == account.id,
        AccountVacancy.responded == True
    )
    stmt = select(Vacancy).where(Vacancy.id.not_in(subq)).order_by(Vacancy.id).limit(
        remaining if not test_mode else 100)
    vacancies = (await session.execute(stmt)).scalars().all()

    if not vacancies:
        logger.debug("No new vacancies for account %d", account.id)
        return []

    logger.info("Account %d: processing %d vacancies", account.id, len(vacancies))
    results = []

    for vacancy in vacancies:
        success = await send_response_for_vacancy(account, vacancy, session, test_mode)
        results.append({
            "vacancy_id": vacancy.id,
            "title": vacancy.title,
            "url": vacancy.url,
            "success": success,
        })

        if not test_mode and success:
            delay = random.randint(account.response_interval_min, account.response_interval_max)
            logger.info("Account %d: waiting %d seconds before next response", account.id, delay)
            await asyncio.sleep(delay)

        if not test_mode and account.responses_today >= account.daily_response_limit:
            break

    return results
