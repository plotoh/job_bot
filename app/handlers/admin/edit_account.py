import logging
from aiogram import types, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.filters import StateFilter

from app.fsm.states import AdminEditStates
from app.services.account import (
    update_account_filter, update_account_resume, update_account_proxy,
    update_account_limit, update_account_limit_range,
    update_account_interval_range, update_account_work_hours,
    update_account_prompt
)
from .accounts import show_account_menu
from .main import admin_main_menu
from ...database.models import AsyncSessionLocal, Account

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_telegram_username")
async def edit_telegram_username_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing telegram username")
    await callback.message.edit_text("Введите новый Telegram username (например, @username) или '-' чтобы удалить:")
    await state.set_state(AdminEditStates.editing_telegram_username)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_telegram_username), F.text)
async def edit_telegram_username_save(message: types.Message, state: FSMContext):
    new_username = message.text.strip()
    if new_username == "-":
        new_username = None
    data = await state.get_data()
    account_id = data["account_id"]
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if account:
            account.telegram_username = new_username
            await session.commit()
            logger.info(f"Admin {message.from_user.id} updated telegram username for account {account_id}")
            await message.answer("✅ Telegram username обновлён!")
        else:
            await message.answer("❌ Аккаунт не найден.")
    # Возвращаемся в меню аккаунта
    from .accounts import show_account_menu
    await show_account_menu(message, account_id, state)


# ----- Фильтр -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_filter")
async def edit_filter_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing filter")
    await callback.message.edit_text("Введите новый URL фильтра (например, ссылка на поиск hh.ru):")
    await state.set_state(AdminEditStates.editing_filter)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_filter), F.text)
async def edit_filter_save(message: types.Message, state: FSMContext):
    new_url = message.text
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_filter(account_id, new_url)
    if success:
        logger.info(f"Admin {message.from_user.id} updated filter for account {account_id} to {new_url}")
        await message.answer("✅ Фильтр обновлён!")
        await show_account_menu(message, account_id, state)
    else:
        await message.answer("❌ Аккаунт не найден.")
        await admin_main_menu(message, state)


# ----- Резюме -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_resume")
async def edit_resume_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing resume")
    await callback.message.edit_text("Отправьте новый текст резюме:")
    await state.set_state(AdminEditStates.editing_resume)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_resume), F.text)
async def edit_resume_save(message: types.Message, state: FSMContext):
    new_resume = message.text
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_resume(account_id, new_resume)
    if success:
        logger.info(f"Admin {message.from_user.id} updated resume for account {account_id}")
        await message.answer("✅ Резюме обновлено!")
        await show_account_menu(message, account_id, state)
    else:
        await message.answer("❌ Аккаунт не найден.")
        await admin_main_menu(message, state)


# ----- Прокси -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_proxy")
async def edit_proxy_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing proxy")
    await callback.message.edit_text(
        "Введите новый прокси (например, http://user:pass@host:port) или '-' для удаления:")
    await state.set_state(AdminEditStates.editing_proxy)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_proxy), F.text)
async def edit_proxy_save(message: types.Message, state: FSMContext):
    new_proxy = message.text.strip()
    if new_proxy == "-":
        new_proxy = None
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_proxy(account_id, new_proxy)
    if success:
        logger.info(f"Admin {message.from_user.id} updated proxy for account {account_id}")
        await message.answer("✅ Прокси обновлён!" if new_proxy else "✅ Прокси удалён.")
        await show_account_menu(message, account_id, state)
    else:
        await message.answer("❌ Аккаунт не найден.")
        await admin_main_menu(message, state)


# ----- Текущий лимит -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_limit")
async def edit_limit_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing daily limit")
    await callback.message.edit_text("Введите новый дневной лимит откликов (целое число):")
    await state.set_state(AdminEditStates.editing_limit)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_limit), F.text)
async def edit_limit_save(message: types.Message, state: FSMContext):
    try:
        new_limit = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_limit(account_id, new_limit)
    if success:
        logger.info(f"Admin {message.from_user.id} set daily limit to {new_limit} for account {account_id}")
        await message.answer("✅ Лимит обновлён!")
        await show_account_menu(message, account_id, state)
    else:
        await message.answer("❌ Аккаунт не найден.")
        await admin_main_menu(message, state)


# ----- Диапазон лимита -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_limit_range")
async def edit_limit_range_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing limit range")
    await callback.message.edit_text("Введите минимальный и максимальный лимит через пробел (например: 50 100):")
    await state.set_state(AdminEditStates.editing_limit_range)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_limit_range), F.text)
async def edit_limit_range_save(message: types.Message, state: FSMContext):
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
        logger.info(f"Admin {message.from_user.id} updated limit range for account {account_id}")
        await message.answer("✅ Диапазон лимита обновлён!")
        await show_account_menu(message, account_id, state)
    else:
        await message.answer("❌ Аккаунт не найден.")
        await admin_main_menu(message, state)


# ----- Интервал отклика -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_interval")
async def edit_interval_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing interval")
    await callback.message.edit_text(
        "Введите минимальный и максимальный интервал между откликами в секундах через пробел (например: 120 480):")
    await state.set_state(AdminEditStates.editing_interval_range)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_interval_range), F.text)
async def edit_interval_save(message: types.Message, state: FSMContext):
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
        logger.info(f"Admin {message.from_user.id} updated interval range for account {account_id}")
        await message.answer("✅ Интервал откликов обновлён!")
        await show_account_menu(message, account_id, state)
    else:
        await message.answer("❌ Аккаунт не найден.")
        await admin_main_menu(message, state)


# ----- Рабочие часы -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_work_hours")
async def edit_work_hours_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing work hours")
    await callback.message.edit_text(
        "Введите часы начала и окончания работы через пробел (например: 10 17):")
    await state.set_state(AdminEditStates.editing_work_hours)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_work_hours), F.text)
async def edit_work_hours_save(message: types.Message, state: FSMContext):
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
        logger.info(f"Admin {message.from_user.id} updated work hours for account {account_id}")
        await message.answer("✅ Рабочие часы обновлены!")
        await show_account_menu(message, account_id, state)
    else:
        await message.answer("❌ Аккаунт не найден.")
        await admin_main_menu(message, state)


# ----- Системный промпт -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_prompt")
async def edit_prompt_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing system prompt")
    await callback.message.edit_text(
        "Введите новый системный промпт (можно использовать Markdown). Отправьте '-' чтобы сбросить к стандартному.")
    await state.set_state(AdminEditStates.editing_prompt)
    await callback.answer()


@router.message(StateFilter(AdminEditStates.editing_prompt), F.text)
async def edit_prompt_save(message: types.Message, state: FSMContext):
    new_prompt = message.text.strip()
    if new_prompt == "-":
        new_prompt = None
    data = await state.get_data()
    account_id = data["account_id"]
    success = await update_account_prompt(account_id, new_prompt)
    if success:
        logger.info(f"Admin {message.from_user.id} updated system prompt for account {account_id}")
        await message.answer("✅ Системный промпт обновлён!")
        await show_account_menu(message, account_id, state)
    else:
        await message.answer("❌ Аккаунт не найден.")
        await admin_main_menu(message, state)
