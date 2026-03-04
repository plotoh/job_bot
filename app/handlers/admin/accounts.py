import logging
from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select

from app.fsm.states import AdminEditStates
from app.services.account import get_account
from app.database.models import AsyncSessionLocal, Account

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(AdminEditStates.choosing_account, F.data.startswith("admin_acc_"))
async def account_selected(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[2])
    logger.info(f"Admin {callback.from_user.id} selected account {account_id}")
    await state.update_data(account_id=account_id)

    account = await get_account(account_id)
    if not account:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text="🧪 Тестовый режим", callback_data="admin_test_mode")],
        [InlineKeyboardButton(text="✏️ Изменить фильтр", callback_data="admin_edit_filter")],
        [InlineKeyboardButton(text="📝 Изменить резюме", callback_data="admin_edit_resume")],
        [InlineKeyboardButton(text="🌐 Изменить прокси", callback_data="admin_edit_proxy")],
        [InlineKeyboardButton(text="🔢 Изменить лимит откликов", callback_data="admin_edit_limit")],
        [InlineKeyboardButton(text="⚙️ Лимит (диапазон)", callback_data="admin_edit_limit_range")],
        [InlineKeyboardButton(text="⏱ Интервал отклика", callback_data="admin_edit_interval")],
        [InlineKeyboardButton(text="🕒 Рабочие часы", callback_data="admin_edit_work_hours")],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_back_to_main")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"Аккаунт: {account.username}\n"
        f"ID: {account.id}\n"
        f"Фильтр: {account.search_filter.get('url', 'не задан')}\n"
        f"Лимит: {account.responses_today}/{account.daily_response_limit}\n"
        f"Прокси: {account.proxy or 'не используется'}",
        reply_markup=keyboard
    )
    await state.set_state(AdminEditStates.choosing_action)
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_main")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    from .main import admin_main_menu
    logger.info(f"Admin {callback.from_user.id} returned to main menu")
    await admin_main_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "admin_refresh_list")
async def refresh_list(callback: CallbackQuery, state: FSMContext):
    from .main import admin_main_menu
    logger.info(f"Admin {callback.from_user.id} refreshed list")
    await admin_main_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "admin_noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "admin_close")
async def close_admin(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} closed admin panel")
    await callback.message.delete()
    await state.clear()
    await callback.answer("Админ-панель закрыта")
