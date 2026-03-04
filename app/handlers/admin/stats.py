import logging
from aiogram import types, F, Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, func
from datetime import date

from app.database.models import AsyncSessionLocal, Account, Response, Invitation

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_global_stats")
async def admin_global_stats(callback: CallbackQuery):
    logger.info(f"Admin {callback.from_user.id} requested global stats")
    async with AsyncSessionLocal() as session:
        total_accounts = await session.scalar(select(func.count(Account.id)))
        total_responses = await session.scalar(select(func.count(Response.id)))
        total_invitations = await session.scalar(select(func.count(Invitation.id)))
        today = date.today()
        active_today = await session.scalar(
            select(func.count(Account.id)).where(Account.last_reset_date == today)
        )

    text = (
        f"📊 <b>Общая статистика</b>\n\n"
        f"👥 Всего аккаунтов: {total_accounts}\n"
        f"📦 Всего откликов: {total_responses}\n"
        f"📬 Всего приглашений: {total_invitations}\n"
        f"📅 Активных сегодня: {active_today}"
    )
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back_to_main")]
    ]))
    await callback.answer()
