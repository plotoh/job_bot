from aiogram import types, F, Router
from sqlalchemy import select, func, and_
from datetime import date

from app.database.models import AsyncSessionLocal, Account, Response, Invitation
from app.keyboards.reply import get_main_keyboard

router = Router()


@router.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        # Получаем аккаунт пользователя
        account = await session.get(Account, telegram_id)
        if not account:
            await message.answer("У вас нет привязанного аккаунта.", reply_markup=get_main_keyboard())
            return

        # Сегодняшние отклики
        today = date.today()
        stmt_today = select(func.count()).where(
            and_(
                Response.account_id == account.id,
                func.date(Response.created_at) == today
            )
        )
        today_responses = await session.scalar(stmt_today) or 0

        # Всего откликов
        total_responses = await session.scalar(
            select(func.count()).where(Response.account_id == account.id)
        ) or 0

        # Приглашения
        total_invitations = await session.scalar(
            select(func.count()).where(Invitation.account_id == account.id)
        ) or 0

        # Дополнительно: лимит на сегодня
        limit_today = account.daily_response_limit
        remaining = max(0, limit_today - account.responses_today)

    text = (
        f"📊 **Статистика для аккаунта {account.username}**\n\n"
        f"📅 Откликов сегодня: {today_responses} (осталось: {remaining})\n"
        f"📦 Всего откликов: {total_responses}\n"
        f"📬 Приглашений на собеседование: {total_invitations}"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
