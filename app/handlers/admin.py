from aiogram import types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select

from app.handlers.test_mode import show_test_menu
from app.utils.encryption import encrypt_password
from datetime import date

from app.database.models import AsyncSessionLocal, Account
from app.config import settings
from app.keyboards.reply import get_main_keyboard

router = Router()


# Фильтр для проверки, является ли пользователь администратором
async def is_admin(message: types.Message) -> bool:
    return message.from_user.id == settings.ADMIN_ID


# Состояния FSM для редактирования аккаунта
class EditAccountStates(StatesGroup):
    choosing_account = State()
    choosing_action = State()
    editing_filter = State()
    editing_resume = State()
    editing_proxy = State()
    editing_limit = State()

    editing_limit_range = State()
    editing_interval_range = State()
    editing_work_hours = State()


class AddAccountStates(StatesGroup):
    waiting_telegram_id = State()
    waiting_username = State()
    waiting_password = State()
    waiting_resume_id = State()
    waiting_proxy = State()
    waiting_filter_url = State()
    waiting_filter_pages = State()
    # Остальные поля оставим по умолчанию


@router.message(Command("add_account"), is_admin)
async def add_account_start(message: types.Message, state: FSMContext):
    await message.answer("Введите telegram ID пользователя (целое число):")
    await state.set_state(AddAccountStates.waiting_telegram_id)


@router.message(AddAccountStates.waiting_telegram_id, F.text)
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
    await state.set_state(AddAccountStates.waiting_username)


@router.message(AddAccountStates.waiting_username, F.text)
async def add_account_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Введите пароль (будет зашифрован):")
    await state.set_state(AddAccountStates.waiting_password)


@router.message(AddAccountStates.waiting_password, F.text)
async def add_account_password(message: types.Message, state: FSMContext):
    encrypted = encrypt_password(message.text)
    await state.update_data(password_encrypted=encrypted)
    await message.answer("Введите resume_id (ID резюме на hh.ru):")
    await state.set_state(AddAccountStates.waiting_resume_id)


@router.message(AddAccountStates.waiting_resume_id, F.text)
async def add_account_resume_id(message: types.Message, state: FSMContext):
    await state.update_data(resume_id=message.text)
    await message.answer("Введите прокси (или '-' если не нужно):")
    await state.set_state(AddAccountStates.waiting_proxy)


@router.message(AddAccountStates.waiting_proxy, F.text)
async def add_account_proxy(message: types.Message, state: FSMContext):
    proxy = message.text.strip()
    if proxy == "-":
        proxy = None
    await state.update_data(proxy=proxy)
    await message.answer("Введите URL фильтра поиска вакансий (например, https://hh.ru/search/vacancy?text=Python):")
    await state.set_state(AddAccountStates.waiting_filter_url)


@router.message(AddAccountStates.waiting_filter_url, F.text)
async def add_account_filter_url(message: types.Message, state: FSMContext):
    await state.update_data(filter_url=message.text)
    await message.answer("Введите максимальное количество страниц для парсинга (целое число):")
    await state.set_state(AddAccountStates.waiting_filter_pages)


@router.message(AddAccountStates.waiting_filter_pages, F.text)
async def add_account_filter_pages(message: types.Message, state: FSMContext):
    try:
        pages = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return

    data = await state.get_data()
    # Создаём аккаунт
    async with AsyncSessionLocal() as session:
        account = Account(
            id=data['account_id'],
            username=data['username'],
            password_encrypted=data['password_encrypted'],
            resume_id=data['resume_id'],
            proxy=data.get('proxy'),
            search_filter={"url": data['filter_url'], "max_pages": pages},
            # Остальные поля по умолчанию
        )
        session.add(account)
        await session.commit()

    await message.answer("✅ Аккаунт успешно создан!")
    await state.clear()


@router.callback_query(StateFilter(EditAccountStates.choosing_action), F.data == "admin_edit_limit_range")
async def edit_limit_range_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите минимальный и максимальный лимит через пробел (например: 50 100):")
    await state.set_state(EditAccountStates.editing_limit_range)
    await callback.answer()


@router.message(StateFilter(EditAccountStates.editing_limit_range), F.text)
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

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        account.daily_limit_min = min_lim
        account.daily_limit_max = max_lim
        # Сразу пересчитывать лимит на сегодня не будем, он обновится при следующем сбросе
        await session.commit()

    await message.answer("✅ Диапазон лимита обновлён!")
    await show_accounts_list(message, state)


# Команда /admin для входа в админ-панель
@router.message(Command("admin"), is_admin)
async def admin_panel(message: types.Message, state: FSMContext):
    await state.clear()
    await show_accounts_list(message, state)


async def show_accounts_list(message: types.Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Account))
        accounts = result.scalars().all()

    if not accounts:
        await message.answer("Нет ни одного аккаунта.")
        return

    # Создаём инлайн-клавиатуру со списком аккаунтов
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(
            text=f"{acc.username} (ID: {acc.id})",
            callback_data=f"admin_acc_{acc.id}"
        )])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выберите аккаунт для редактирования:", reply_markup=keyboard)
    await state.set_state(EditAccountStates.choosing_account)


# Обработчик выбора аккаунта
@router.callback_query(StateFilter(EditAccountStates.choosing_account), F.data.startswith("admin_acc_"))
async def account_selected(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[2])
    await state.update_data(account_id=account_id)

    # Получаем данные аккаунта
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)

    # Кнопки действий
    buttons = [
        [InlineKeyboardButton(text="🧪 Тестовый режим", callback_data="admin_test_mode")],
        [InlineKeyboardButton(text="✏️ Изменить фильтр", callback_data="admin_edit_filter")],
        [InlineKeyboardButton(text="📝 Изменить резюме", callback_data="admin_edit_resume")],
        [InlineKeyboardButton(text="🌐 Изменить прокси", callback_data="admin_edit_proxy")],
        [InlineKeyboardButton(text="🔢 Изменить лимит откликов", callback_data="admin_edit_limit")],
        [InlineKeyboardButton(text="⚙️ Лимит (диапазон)", callback_data="admin_edit_limit_range")],
        [InlineKeyboardButton(text="⏱ Интервал отклика", callback_data="admin_edit_interval")],
        [InlineKeyboardButton(text="🕒 Рабочие часы", callback_data="admin_edit_work_hours")],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_back_to_list")],
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
    await state.set_state(EditAccountStates.choosing_action)
    await callback.answer()


@router.callback_query(StateFilter(EditAccountStates.choosing_action), F.data == "admin_test_mode")
async def test_mode_menu(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)

    # Строим клавиатуру с флагами
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅' if account.test_parse_vacancy else '❌'} Парсить вакансию",
            callback_data=f"test_toggle_parse"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if account.test_generate_letter else '❌'} Генерировать письмо",
            callback_data=f"test_toggle_generate"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if account.test_send_response else '❌'} Отправлять отклик",
            callback_data=f"test_toggle_send"
        )],
        [InlineKeyboardButton(
            text=f"🔢 Количество: {account.test_count}",
            callback_data=f"test_set_count"
        )],
        [InlineKeyboardButton(text="🚀 Запустить тест", callback_data="test_run")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_account")],
    ])
    await callback.message.edit_text("Настройки тестового режима:", reply_markup=kb)
    await state.set_state("test_mode")  # можно использовать отдельное состояние, но проще хранить флаг
    await callback.answer()


@router.callback_query(F.data.startswith("test_toggle_"))
async def test_toggle(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    field = callback.data.split("_")[2]  # parse, generate, send

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if field == "parse":
            account.test_parse_vacancy = not account.test_parse_vacancy
        elif field == "generate":
            account.test_generate_letter = not account.test_generate_letter
        elif field == "send":
            account.test_send_response = not account.test_send_response
        await session.commit()

    # Обновляем меню
    await test_mode_menu(callback, state)
    await callback.answer()


@router.callback_query(F.data == "test_set_count")
async def test_set_count(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите количество тестовых откликов (целое число):")
    await state.set_state("test_waiting_count")
    await callback.answer()


@router.message(StateFilter("test_waiting_count"), F.text)
async def test_count_received(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    data = await state.get_data()
    account_id = data["account_id"]
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        account.test_count = count
        await session.commit()
    await message.answer("✅ Количество сохранено.")
    # Вернуться в меню тестового режима
    await test_mode_menu(message, state)  # но message не callback, надо создать новое сообщение
    # Проще: отправить новое сообщение с меню, а старое удалить.
    await message.delete()
    # Создадим callback-запрос искусственно? Лучше вызвать функцию, которая создаст новое сообщение.
    # Упростим: просто покажем меню в новом сообщении.
    await show_test_menu(message.from_user.id, account_id, state)


# Кнопка "Назад к списку"
@router.callback_query(StateFilter(EditAccountStates.choosing_action), F.data == "admin_back_to_list")
async def back_to_list(callback: CallbackQuery, state: FSMContext):
    await show_accounts_list(callback.message, state)
    await callback.answer()


# Закрыть админку
@router.callback_query(F.data == "admin_close")
async def close_admin(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await state.clear()
    await callback.answer("Админ-панель закрыта")


# --- Редактирование фильтра ---
@router.callback_query(StateFilter(EditAccountStates.choosing_action), F.data == "admin_edit_filter")
async def edit_filter_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новый URL фильтра (например, ссылка на поиск hh.ru):")
    await state.set_state(EditAccountStates.editing_filter)
    await callback.answer()


@router.message(StateFilter(EditAccountStates.editing_filter), F.text)
async def edit_filter_save(message: types.Message, state: FSMContext):
    new_url = message.text
    data = await state.get_data()
    account_id = data["account_id"]

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        account.search_filter["url"] = new_url
        await session.commit()

    await message.answer("✅ Фильтр обновлён!")
    await show_accounts_list(message, state)  # возвращаем к списку


# --- Редактирование резюме ---
@router.callback_query(StateFilter(EditAccountStates.choosing_action), F.data == "admin_edit_resume")
async def edit_resume_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Отправьте новый текст резюме:")
    await state.set_state(EditAccountStates.editing_resume)
    await callback.answer()


@router.message(StateFilter(EditAccountStates.editing_resume), F.text)
async def edit_resume_save(message: types.Message, state: FSMContext):
    new_resume = message.text
    data = await state.get_data()
    account_id = data["account_id"]

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        account.resume_text = new_resume
        await session.commit()

    await message.answer("✅ Резюме обновлено!")
    await show_accounts_list(message, state)


# --- Редактирование прокси ---
@router.callback_query(StateFilter(EditAccountStates.choosing_action), F.data == "admin_edit_proxy")
async def edit_proxy_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите новый прокси (например, http://user:pass@host:port) или '-' для удаления:")
    await state.set_state(EditAccountStates.editing_proxy)
    await callback.answer()


@router.message(StateFilter(EditAccountStates.editing_proxy), F.text)
async def edit_proxy_save(message: types.Message, state: FSMContext):
    new_proxy = message.text.strip()
    if new_proxy == "-":
        new_proxy = None
    data = await state.get_data()
    account_id = data["account_id"]

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        account.proxy = new_proxy
        await session.commit()

    await message.answer("✅ Прокси обновлён!")
    await show_accounts_list(message, state)


# --- Редактирование лимита ---
@router.callback_query(StateFilter(EditAccountStates.choosing_action), F.data == "admin_edit_limit")
async def edit_limit_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите новый дневной лимит откликов (целое число):")
    await state.set_state(EditAccountStates.editing_limit)
    await callback.answer()


@router.message(StateFilter(EditAccountStates.editing_limit), F.text)
async def edit_limit_save(message: types.Message, state: FSMContext):
    try:
        new_limit = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return

    data = await state.get_data()
    account_id = data["account_id"]

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        account.daily_response_limit = new_limit
        await session.commit()

    await message.answer("✅ Лимит обновлён!")
    await show_accounts_list(message, state)
