import logging
from aiogram import types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, func
from datetime import date

from app.config import settings
from app.database.models import AsyncSessionLocal, Account, Response, Invitation
from app.fsm.states import AdminEditStates, AdminAddAccountStates
from app.services.account import (
    get_all_accounts, create_account,
    update_account_filter, update_account_resume, update_account_proxy, update_account_limit_range,
    update_account_interval_range, update_account_work_hours,
    update_account_prompt, update_account_telegram_username, get_account_with_reset
)
from app.services.account_data import format_admin_account_text
from app.handlers.test_mode import show_test_menu
from app.utils.encryption import encrypt_password

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID


# Главное меню админа
async def admin_main_menu(message: types.Message, state: FSMContext):
    accounts = await get_all_accounts()
    action_buttons = [
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="admin_add_account")],
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_global_stats")],
        [InlineKeyboardButton(text="🔄 Обновить список", callback_data="admin_refresh_list")],
    ]
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


# Обновление списка
@router.callback_query(F.data == "admin_refresh_list")
async def refresh_list(callback: CallbackQuery, state: FSMContext):
    await admin_main_menu(callback.message, state)
    await callback.answer()


# Пустышка для "нет аккаунтов"
@router.callback_query(F.data == "admin_noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


# Выбор аккаунта
@router.callback_query(StateFilter(AdminEditStates.choosing_account), F.data.startswith("admin_acc_"))
async def account_selected(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[2])
    await state.update_data(account_id=account_id)

    account = await get_account_with_reset(account_id)  # используем сброс
    if not account:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return

    text = format_admin_account_text(account)
    buttons = [
        [InlineKeyboardButton(text="🧪 Тестовый режим", callback_data="admin_test_mode")],
        [InlineKeyboardButton(text="✏️ Изменить фильтр", callback_data="admin_edit_filter")],
        [InlineKeyboardButton(text="📝 Изменить резюме", callback_data="admin_edit_resume")],
        [InlineKeyboardButton(text="🌐 Изменить прокси", callback_data="admin_edit_proxy")],
        # Убрана кнопка "🔢 Изменить лимит откликов"
        [InlineKeyboardButton(text="⚙️ Лимит (диапазон)", callback_data="admin_edit_limit_range")],
        [InlineKeyboardButton(text="⏱ Интервал отклика", callback_data="admin_edit_interval")],
        [InlineKeyboardButton(text="🕒 Рабочие часы", callback_data="admin_edit_work_hours")],
        [InlineKeyboardButton(text="🤖 Системный промпт", callback_data="admin_edit_prompt")],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_back_to_main")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(AdminEditStates.choosing_action)
    await callback.answer()


# Назад к списку
@router.callback_query(F.data == "admin_back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await admin_main_menu(callback.message, state)
    await callback.answer()


# Закрыть админку
@router.callback_query(F.data == "admin_close")
async def close_admin(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()
    await callback.answer("Админ-панель закрыта")


# Общая статистика
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
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back_to_main")]
    ]))
    await callback.answer()


# Тестовый режим
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_test_mode")
async def admin_test_mode(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
    await show_test_menu(callback, account, state, is_admin=True)


# ----- Редактирование Telegram username -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_telegram_username")
async def edit_telegram_username_start(callback: CallbackQuery, state: FSMContext):
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
    success = await update_account_telegram_username(account_id, new_username)
    if success:
        await message.answer("✅ Telegram username обновлён!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    # Возвращаемся в меню аккаунта
    await account_selected_by_id(message, account_id, state)


# ----- Фильтр -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_filter")
async def edit_filter_start(callback: CallbackQuery, state: FSMContext):
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
        await message.answer("✅ Фильтр обновлён!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await account_selected_by_id(message, account_id, state)


# ----- Резюме -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_resume")
async def edit_resume_start(callback: CallbackQuery, state: FSMContext):
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
        await message.answer("✅ Резюме обновлено!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await account_selected_by_id(message, account_id, state)


# ----- Прокси -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_proxy")
async def edit_proxy_start(callback: CallbackQuery, state: FSMContext):
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
        await message.answer("✅ Прокси обновлён!" if new_proxy else "✅ Прокси удалён.")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await account_selected_by_id(message, account_id, state)


# ----- Диапазон лимита -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_limit_range")
async def edit_limit_range_start(callback: CallbackQuery, state: FSMContext):
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
        await message.answer("✅ Диапазон лимита обновлён!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await account_selected_by_id(message, account_id, state)


# ----- Интервал отклика -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_interval")
async def edit_interval_start(callback: CallbackQuery, state: FSMContext):
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
        await message.answer("✅ Интервал откликов обновлён!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await account_selected_by_id(message, account_id, state)


# ----- Рабочие часы -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_work_hours")
async def edit_work_hours_start(callback: CallbackQuery, state: FSMContext):
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
        await message.answer("✅ Рабочие часы обновлены!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await account_selected_by_id(message, account_id, state)


# ----- Системный промпт -----
@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_prompt")
async def edit_prompt_start(callback: CallbackQuery, state: FSMContext):
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
        await message.answer("✅ Системный промпт обновлён!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await account_selected_by_id(message, account_id, state)


# ----- Вспомогательная функция для возврата в меню аккаунта -----
async def account_selected_by_id(update: types.Message | CallbackQuery, account_id: int, state: FSMContext):
    # Эмулируем выбор аккаунта, чтобы показать меню
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
    text = format_admin_account_text(account)
    buttons = [
        [InlineKeyboardButton(text="🧪 Тестовый режим", callback_data="admin_test_mode")],
        [InlineKeyboardButton(text="✏️ Изменить фильтр", callback_data="admin_edit_filter")],
        [InlineKeyboardButton(text="📝 Изменить резюме", callback_data="admin_edit_resume")],
        [InlineKeyboardButton(text="🌐 Изменить прокси", callback_data="admin_edit_proxy")],
        [InlineKeyboardButton(text="🔢 Изменить лимит откликов", callback_data="admin_edit_limit")],
        [InlineKeyboardButton(text="⚙️ Лимит (диапазон)", callback_data="admin_edit_limit_range")],
        [InlineKeyboardButton(text="⏱ Интервал отклика", callback_data="admin_edit_interval")],
        [InlineKeyboardButton(text="🕒 Рабочие часы", callback_data="admin_edit_work_hours")],
        [InlineKeyboardButton(text="🤖 Системный промпт", callback_data="admin_edit_prompt")],
        [InlineKeyboardButton(text="📱 Telegram username", callback_data="admin_edit_telegram_username")],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_back_to_main")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(update, types.Message):
        await update.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await update.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(account_id=account_id)
    await state.set_state(AdminEditStates.choosing_action)


# ----- Добавление аккаунта -----
@router.callback_query(F.data == "admin_add_account")
async def add_account_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите telegram ID пользователя (целое число):")
    await state.set_state(AdminAddAccountStates.waiting_telegram_id)
    await callback.answer()


@router.message(AdminAddAccountStates.waiting_telegram_id, F.text)
async def add_account_telegram_id(message: types.Message, state: FSMContext):
    try:
        telegram_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return

    async with AsyncSessionLocal() as session:
        existing = await session.get(Account, telegram_id)
        if existing:
            await message.answer("❌ Аккаунт с таким telegram ID уже существует.")
            return
        await state.update_data(account_id=telegram_id)

    await message.answer("Введите username (логин на hh.ru):")
    await state.set_state(AdminAddAccountStates.waiting_username)


@router.message(AdminAddAccountStates.waiting_username, F.text)
async def add_account_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Введите пароль (будет зашифрован):")
    await state.set_state(AdminAddAccountStates.waiting_password)


@router.message(AdminAddAccountStates.waiting_password, F.text)
async def add_account_password(message: types.Message, state: FSMContext):
    encrypted = encrypt_password(message.text)
    await state.update_data(password_encrypted=encrypted)
    await message.answer("Введите resume_id (ID резюме на hh.ru):")
    await state.set_state(AdminAddAccountStates.waiting_resume_id)


@router.message(AdminAddAccountStates.waiting_resume_id, F.text)
async def add_account_resume_id(message: types.Message, state: FSMContext):
    await state.update_data(resume_id=message.text)
    await message.answer("Введите прокси (или '-' если не нужно):")
    await state.set_state(AdminAddAccountStates.waiting_proxy)


@router.message(AdminAddAccountStates.waiting_proxy, F.text)
async def add_account_proxy(message: types.Message, state: FSMContext):
    proxy = message.text.strip()
    if proxy == "-":
        proxy = None
    await state.update_data(proxy=proxy)
    await message.answer("Введите URL фильтра поиска вакансий (например, https://hh.ru/search/vacancy?text=Python):")
    await state.set_state(AdminAddAccountStates.waiting_filter_url)


@router.message(AdminAddAccountStates.waiting_filter_url, F.text)
async def add_account_filter_url(message: types.Message, state: FSMContext):
    await state.update_data(filter_url=message.text)
    await message.answer("Введите максимальное количество страниц для парсинга (целое число):")
    await state.set_state(AdminAddAccountStates.waiting_filter_pages)


@router.message(AdminAddAccountStates.waiting_filter_pages, F.text)
async def add_account_filter_pages(message: types.Message, state: FSMContext):
    try:
        pages = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return

    data = await state.get_data()
    success = await create_account({
        'account_id': data['account_id'],
        'username': data['username'],
        'password_encrypted': data['password_encrypted'],
        'resume_id': data['resume_id'],
        'proxy': data.get('proxy'),
        'filter_url': data['filter_url'],
        'max_pages': pages,
    })
    if success:
        await message.answer("✅ Аккаунт успешно создан!")
    else:
        await message.answer("❌ Ошибка при создании аккаунта.")
    await state.clear()
    await admin_main_menu(message, state)
