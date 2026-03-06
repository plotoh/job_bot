import logging

from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.fsm.states import AdminEditStates
from app.handlers.common_edit import start_editing
from app.handlers.test_mode import show_test_menu
from app.services import account_crud as crud
from app.services.exceptions import ObjectNotFound

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_test_mode")
async def admin_test_mode(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data.get("account_id")
    if not account_id:
        await callback.answer("❌ Аккаунт не выбран", show_alert=True)
        return
    try:
        account = await crud.get_account_with_reset(account_id)
    except ObjectNotFound:
        await callback.message.edit_text("❌ Аккаунт не найден.")
        return
    await show_test_menu(callback, account, state, is_admin=True)


# ----- Все обработчики редактирования полей теперь идут через start_editing -----

@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_telegram_username")
async def edit_telegram_username_start(callback: CallbackQuery, state: FSMContext):
    await start_editing(callback, state, field='telegram_username', mode='admin')


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_filter")
async def edit_filter_start(callback: CallbackQuery, state: FSMContext):
    await start_editing(callback, state, field='filter', mode='admin')


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_resume")
async def edit_resume_start(callback: CallbackQuery, state: FSMContext):
    await start_editing(callback, state, field='resume', mode='admin')


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_proxy")
async def edit_proxy_start(callback: CallbackQuery, state: FSMContext):
    await start_editing(callback, state, field='proxy', mode='admin')


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_limit_range")
async def edit_limit_range_start(callback: CallbackQuery, state: FSMContext):
    await start_editing(callback, state, field='limit_range', mode='admin')


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_interval")
async def edit_interval_start(callback: CallbackQuery, state: FSMContext):
    await start_editing(callback, state, field='interval_range', mode='admin')


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_work_hours")
async def edit_work_hours_start(callback: CallbackQuery, state: FSMContext):
    await start_editing(callback, state, field='work_hours', mode='admin')


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_max_pages")
async def edit_max_pages_start(callback: CallbackQuery, state: FSMContext):
    await start_editing(callback, state, field='max_pages', mode='admin')