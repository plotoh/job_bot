# app/handlers/admin/common.py
import logging
from typing import Union

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.database.models import AsyncSessionLocal, Account
from app.services.account_data import format_admin_account_text
from app.keyboards.inline import get_account_edit_keyboard

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    from app.config import settings
    return user_id == settings.ADMIN_ID


async def get_account_with_check(account_id: int) -> Account | None:
    """Получает аккаунт из БД с проверкой существования."""
    async with AsyncSessionLocal() as session:
        return await session.get(Account, account_id)


async def show_account_menu(
        update: Union[types.Message, types.CallbackQuery],
        account_id: int,
        state: FSMContext,
) -> None:
    """Показывает меню управления конкретным аккаунтом."""
    account = await get_account_with_check(account_id)
    if not account:
        text = "❌ Аккаунт не найден."
        if isinstance(update, types.Message):
            await update.answer(text)
        else:
            await update.message.edit_text(text)
        return

    text = format_admin_account_text(account)
    keyboard = get_account_edit_keyboard()

    if isinstance(update, types.Message):
        await update.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    await state.update_data(account_id=account_id)
    # Состояние остаётся прежним (choosing_action) – зададим его позже
