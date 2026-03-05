# app/handlers/admin/main.py
import logging
from datetime import date

from aiogram import types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, func

from app.config import settings
from app.database.models import AsyncSessionLocal, Account, Response, Invitation
from app.fsm.states import AdminEditStates
from app.services.account_crud import get_all_accounts, get_account_with_reset
from app.handlers.admin.common import is_admin, show_account_menu
from app.keyboards.inline import get_admin_main_keyboard

logger = logging.getLogger(__name__)
router = Router()


async def admin_main_menu(message: types.Message, state: FSMContext):
    """Отображает главное меню админ-панели."""
    accounts = await get_all_accounts()
    keyboard = get_admin_main_keyboard(accounts)
    await message.answer("👑 Админ-панель\nВыберите действие или аккаунт:", reply_markup=keyboard)
    await state.set_state(AdminEditStates.choosing_account)


@router.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await admin_main_menu(message, state)


@router.message(F.text == "👑 Админ-панель")
async def admin_button_handler(message: types.Message, state: FSMContext):
    if is_admin(message.from_user.id):
        await admin_panel(message, state)
    else:
        await message.answer("У вас нет доступа.")


@router.callback_query(F.data == "admin_refresh_list")
async def refresh_list(callback: CallbackQuery, state: FSMContext):
    await admin_main_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "admin_noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(StateFilter(AdminEditStates.choosing_account), F.data.startswith("admin_acc_"))
async def account_selected(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[2])
    account = await get_account_with_reset(account_id)
    if not account:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return

    await show_account_menu(callback, account_id, state)
    await state.set_state(AdminEditStates.choosing_action)
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await admin_main_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "admin_close")
async def close_admin(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()
    await callback.answer("Админ-панель закрыта")


@router.callback_query(F.data == "admin_global_stats")
async def admin_global_stats(callback: CallbackQuery):
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
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back_to_main")]
        ])
    )
    await callback.answer()