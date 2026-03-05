# app/handlers/admin/edit_account.py
"""
обработчики для редактирования всех полей аккаунта: фильтр, резюме, прокси, лимиты,
интервалы, рабочие часы, telegram username, max_pages, а также тестовый режим.
"""

import logging
from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ForceReply

from app.fsm.states import AdminEditStates
from app.services.account_crud import (
    update_account_filter, update_account_resume, update_account_proxy,
    update_account_limit_range, update_account_interval_range,
    update_account_work_hours, update_account_telegram_username,
    update_account_max_pages,
)
from app.handlers.admin.common import show_account_menu
from app.handlers.test_mode import show_test_menu

logger = logging.getLogger(__name__)
router = Router()


# ----- Тестовый режим -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_test_mode")
async def admin_test_mode(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
    await show_test_menu(callback, account, state, is_admin=True)


# ----- Telegram username -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_telegram_username")
async def edit_telegram_username_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новый Telegram username (например, @username) или '-' чтобы удалить:")
    await state.set_state(AdminEditStates.editing_telegram_username)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_telegram_username), F.text)
async def edit_telegram_username_save(message: Message, state: FSMContext):
    new_username = message.text.strip()
    if new_username == "-":
        new_username = None
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_telegram_username(account_id, new_username)
    if success:
        await message.answer("✅ Telegram username обновлён!")
        logger.info("Admin updated telegram_username for account %d", account_id)
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_account_menu(message, account_id, state)


# ----- Фильтр -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_filter")
async def edit_filter_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новый URL фильтра (например, ссылка на поиск hh.ru):")
    await state.set_state(AdminEditStates.editing_filter)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_filter), F.text)
async def edit_filter_save(message: Message, state: FSMContext):
    new_url = message.text.strip()
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_filter(account_id, new_url)
    if success:
        await message.answer("✅ Фильтр обновлён!")
        logger.info("Admin updated filter for account %d", account_id)
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_account_menu(message, account_id, state)


# ----- Резюме -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_resume")
async def edit_resume_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Отправьте новый текст резюме:")
    await state.set_state(AdminEditStates.editing_resume)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_resume), F.text)
async def edit_resume_save(message: Message, state: FSMContext):
    new_resume = message.text.strip()
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_resume(account_id, new_resume)
    if success:
        await message.answer("✅ Резюме обновлено!")
        logger.info("Admin updated resume for account %d", account_id)
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_account_menu(message, account_id, state)


# ----- Прокси -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_proxy")
async def edit_proxy_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите новый прокси (например, http://user:pass@host:port) или '-' для удаления:"
    )
    await state.set_state(AdminEditStates.editing_proxy)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_proxy), F.text)
async def edit_proxy_save(message: Message, state: FSMContext):
    new_proxy = message.text.strip()
    if new_proxy == "-":
        new_proxy = None
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_proxy(account_id, new_proxy)
    if success:
        await message.answer("✅ Прокси обновлён!" if new_proxy else "✅ Прокси удалён.")
        logger.info("Admin updated proxy for account %d", account_id)
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_account_menu(message, account_id, state)


# ----- Диапазон лимита -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_limit_range")
async def edit_limit_range_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите минимальный и максимальный лимит через пробел (например: 50 100):")
    await state.set_state(AdminEditStates.editing_limit_range)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_limit_range), F.text)
async def edit_limit_range_save(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ Нужно два числа через пробел.")
        return
    try:
        min_lim, max_lim = map(int, parts)
    except ValueError:
        await message.answer("❌ Введите целые числа.")
        return
    if min_lim > max_lim or min_lim <= 0:
        await message.answer("❌ Некорректный диапазон.")
        return
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_limit_range(account_id, min_lim, max_lim)
    if success:
        await message.answer("✅ Диапазон лимита обновлён!")
        logger.info("Admin updated limit range for account %d", account_id)
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_account_menu(message, account_id, state)


# ----- Интервал отклика -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_interval")
async def edit_interval_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите минимальный и максимальный интервал между откликами в секундах через пробел (например: 120 480):"
    )
    await state.set_state(AdminEditStates.editing_interval_range)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_interval_range), F.text)
async def edit_interval_save(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ Нужно два числа через пробел.")
        return
    try:
        min_int, max_int = map(int, parts)
    except ValueError:
        await message.answer("❌ Введите целые числа.")
        return
    if min_int > max_int or min_int <= 0:
        await message.answer("❌ Некорректный диапазон.")
        return
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_interval_range(account_id, min_int, max_int)
    if success:
        await message.answer("✅ Интервал откликов обновлён!")
        logger.info("Admin updated interval range for account %d", account_id)
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_account_menu(message, account_id, state)


# ----- Рабочие часы -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_work_hours")
async def edit_work_hours_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите часы начала и окончания работы через пробел (например: 10 17):"
    )
    await state.set_state(AdminEditStates.editing_work_hours)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_work_hours), F.text)
async def edit_work_hours_save(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ Нужно два числа через пробел.")
        return
    try:
        start, end = map(int, parts)
    except ValueError:
        await message.answer("❌ Введите целые числа.")
        return
    if not (0 <= start < 24) or not (0 <= end <= 24) or start >= end:
        await message.answer("❌ Некорректные часы (должны быть 0-23, начало < конец).")
        return
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_work_hours(account_id, start, end)
    if success:
        await message.answer("✅ Рабочие часы обновлены!")
        logger.info("Admin updated work hours for account %d", account_id)
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_account_menu(message, account_id, state)


# ----- Количество страниц парсинга -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_max_pages")
async def edit_max_pages_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите новое максимальное количество страниц для парсинга (целое число, например 3):"
    )
    await state.set_state(AdminEditStates.editing_max_pages)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_max_pages), F.text)
async def edit_max_pages_save(message: Message, state: FSMContext):
    try:
        max_pages = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if max_pages <= 0:
        await message.answer("❌ Число должно быть положительным.")
        return

    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_max_pages(account_id, max_pages)
    if success:
        await message.answer("✅ Количество страниц обновлено!")
        logger.info("Admin updated max_pages for account %d", account_id)
    else:
        await message.answer("❌ Аккаунт не найден.")
        return
    await show_account_menu(message, account_id, state)