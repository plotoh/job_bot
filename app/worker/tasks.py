from typing import Dict

from app.config import settings
from app.utils.proxy_rotator import get_proxy_for_account
from app.worker.celery_app import celery_app
from app.database.models import AsyncSessionLocal, Account, Vacancy, Response, Invitation
from app.services.hh_parser import HHParser
from app.services.vacancy_filter import extract_secret_word, is_backend_python_keywords  # или is_backend_python_llm
from app.services.letter_generator import generate_cover_letter
import asyncio
import logging
from app.worker.celery_app import celery_app
from app.database.models import AsyncSessionLocal, Account
from sqlalchemy import select
import asyncio

logger = logging.getLogger(__name__)

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@celery_app.task
def parse_new_vacancies_for_account(account_id: int):
    run_async(_parse_new_vacancies(account_id))


@celery_app.task
def check_invitations_for_account(account_id: int):
    run_async(_check_invitations(account_id))

async def _check_invitations(account_id: int):
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account or not account.is_active:
            return

        # Используем cookies, сохранённые в БД (если есть)
        cookies = account.cookies if account.cookies else None
        proxy = get_proxy_for_account(account_id)

        parser = HHParser(account_id, proxy=proxy)
        # Здесь нужно передать cookies в браузер — доработайте метод fetch_invitations, чтобы он принимал cookies
        # Либо реализовать авторизацию отдельно

        try:
            invitations = await parser.fetch_invitations()
        except Exception as e:
            logger.error(f"Failed to fetch invitations for account {account_id}: {e}")
            return

        # Для каждого приглашения проверяем, есть ли уже в БД
        for inv in invitations:
            existing = await session.execute(
                select(Invitation).where(
                    Invitation.account_id == account_id,
                    Invitation.vacancy_hh_id == inv["vacancy_hh_id"],
                    Invitation.invited_at == inv["invited_at"]
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Сохраняем новое приглашение
            new_inv = Invitation(
                account_id=account_id,
                vacancy_hh_id=inv["vacancy_hh_id"],
                company=inv["company"],
                message=inv["message"],
                invited_at=inv["invited_at"]
            )
            session.add(new_inv)
            await session.commit()

            # Отправляем уведомление в Telegram
            await notify_about_invitation(account_id, inv)

async def notify_about_invitation(account_id: int, invitation: Dict):
    """Отправляет сообщение админу или в чат аккаунта."""
    from app.bot_instance import bot  # нужно организовать доступ к боту
    admin_chat_id = settings.ADMIN_CHAT_ID  # добавить в config
    text = (
        f"🎉 Новое приглашение!\n"
        f"Аккаунт: {account_id}\n"
        f"Вакансия: {invitation['vacancy_title']}\n"
        f"Компания: {invitation['company']}\n"
        f"Дата: {invitation['invited_at']}\n"
        f"Сообщение: {invitation['message'] or '—'}"
    )
    await bot.send_message(admin_chat_id, text)


async def _parse_new_vacancies(account_id: int):
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if not account or not account.is_active:
            return

        search_filter = account.search_filter
        parser = HHParser(account_id)
        vacancies = await parser.search_vacancies(
            search_url=search_filter.get("url", "https://hh.ru/search/vacancy?text=Python&area=1"),
            max_pages=search_filter.get("max_pages", 1)
        )

        for vac in vacancies:
            # Проверяем, есть ли уже такая вакансия в БД
            existing = await session.execute(
                select(Vacancy).where(Vacancy.hh_id == vac["id"])
            )
            if existing.scalar_one_or_none():
                continue

            # Парсим детали
            details = await parser.parse_vacancy_details(vac["link"])
            if "error" in details:
                logger.error(f"Error parsing {vac['link']}: {details['error']}")
                continue

            # Проверка соответствия (ключевыми словами, можно заменить на LLM)
            if not is_backend_python_keywords(vac["title"], details.get("description", "")):
                logger.info(f"Vacancy {vac['title']} does not match backend Python, skipping")
                continue

            # Извлекаем проверочное слово
            secret = extract_secret_word(details.get("description", ""))

            # Сохраняем вакансию
            new_vac = Vacancy(
                account_id=account_id,
                hh_id=vac["id"],
                title=vac["title"],
                url=vac["link"],
                description=details.get("description", ""),
                check_word=secret
            )
            session.add(new_vac)
            await session.commit()
            await session.refresh(new_vac)

            # Генерируем письмо
            company = "Компания"  # можно парсить отдельно
            letter = await generate_cover_letter(
                vacancy_title=vac["title"],
                vacancy_description=details.get("description", ""),
                company=company,
                resume_text=account.resume_text,
                secret_word=secret
            )

            # Сохраняем отклик
            response = Response(
                account_id=account_id,
                vacancy_id=new_vac.id,
                cover_letter=letter,
                status="pending"
            )
            session.add(response)
            await session.commit()

            logger.info(f"Generated response for vacancy {vac['title']}")

@celery_app.task
def parse_new_vacancies_for_all_accounts():
    """Запускает парсинг для всех активных аккаунтов."""
    run_async(_parse_all_accounts())

async def _parse_all_accounts():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.is_active == True))
        accounts = result.scalars().all()
        for account in accounts:
            parse_new_vacancies_for_account.delay(account.id)

@celery_app.task
def check_invitations_for_all_accounts():
    """Проверяет приглашения для всех активных аккаунтов."""
    run_async(_check_invitations_all())

async def _check_invitations_all():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account).where(Account.is_active == True))
        accounts = result.scalars().all()
        for account in accounts:
            check_invitations_for_account.delay(account.id)