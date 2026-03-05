import logging
from aiogram import types, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.config import settings
from app.fsm.states import AdminEditStates
from app.handlers.admin.vacancies import show_vacancies_page
from app.services.account import get_all_accounts
from app.keyboards.reply import get_main_keyboard

logger = logging.getLogger(__name__)
router = Router()


def is_admin(message: types.Message) -> bool:
    return message.from_user.id == settings.ADMIN_ID


async def admin_main_menu(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Admin {user_id} opened admin main menu")

    accounts = await get_all_accounts()

    # Кнопки действий
    action_buttons = [
        [InlineKeyboardButton(text="📋 Все вакансии", callback_data="admin_list_vacancies")],
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="admin_add_account")],
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_global_stats")],
        [InlineKeyboardButton(text="🔄 Обновить список", callback_data="admin_refresh_list")],
    ]

    # Кнопки аккаунтов
    account_buttons = []
    for acc in accounts:
        account_buttons.append([InlineKeyboardButton(
            text=f"{acc.username} (ID: {acc.id})",
            callback_data=f"admin_acc_{acc.id}"
        )])

    if not account_buttons:
        account_buttons.append([InlineKeyboardButton(text="📭 Нет аккаунтов", callback_data="admin_noop")])

    close_button = [[InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]]

    keyboard = InlineKeyboardMarkup(inline_keyboard=action_buttons + account_buttons + close_button)
    await message.answer("👑 Админ-панель\nВыберите действие или аккаунт:", reply_markup=keyboard)
    await state.set_state(AdminEditStates.choosing_account)


@router.callback_query(F.data == "admin_list_vacancies")
async def admin_list_vacancies(callback: CallbackQuery):
    logger.info(f"Admin {callback.from_user.id} requested vacancies list")
    await show_vacancies_page(callback.message, 0)
    await callback.answer()


@router.message(Command("admin"), is_admin)
async def admin_panel(message: types.Message, state: FSMContext):
    logger.info(f"Admin {message.from_user.id} used /admin")
    await state.clear()
    await admin_main_menu(message, state)


@router.message(F.text == "👑 Админ-панель")
async def admin_button_handler(message: types.Message, state: FSMContext):
    if is_admin(message):
        await admin_panel(message, state)
    else:
        await message.answer("У вас нет доступа.", reply_markup=get_main_keyboard(message.from_user.id))
