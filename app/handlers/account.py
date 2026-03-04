from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ForceReply

from app.database.models import AsyncSessionLocal, Account
from aiogram.fsm.state import State, StatesGroup

from app.keyboards.reply import get_main_keyboard
from app.utils.encryption import encrypt_password
from aiogram import Router

router = Router()

# app/handlers/account.py (дополнить)
from aiogram.fsm.state import State, StatesGroup


class AccountSettingsStates(StatesGroup):
    choosing_field = State()
    waiting_username = State()
    waiting_password = State()
    waiting_proxy = State()
    waiting_resume = State()
    waiting_filter = State()
    waiting_limit_min = State()
    waiting_limit_max = State()
    waiting_interval_min = State()
    waiting_interval_max = State()
    waiting_work_start = State()
    waiting_work_end = State()


async def show_settings_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔑 Логин/пароль hh")],
        [KeyboardButton(text="📄 Текст резюме")],
        [KeyboardButton(text="🔎 Фильтр поиска (URL)")],
        [KeyboardButton(text="🌐 Прокси")],
        [KeyboardButton(text="⏱ Лимиты и интервалы")],
        [KeyboardButton(text="🕒 Рабочее время")],
        [KeyboardButton(text="◀️ Назад")],
    ], resize_keyboard=True)
    await message.answer("Выберите, что хотите изменить:", reply_markup=kb)
    await state.set_state(AccountSettingsStates.choosing_field)


@router.message(F.text == "⚙️ Настройки аккаунта")
async def account_settings_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔑 Логин/пароль hh")],
        [KeyboardButton(text="📄 Текст резюме")],
        [KeyboardButton(text="🔎 Фильтр поиска (URL)")],
        [KeyboardButton(text="🌐 Прокси")],
        [KeyboardButton(text="⏱ Лимиты и интервалы")],
        [KeyboardButton(text="🕒 Рабочее время")],
        [KeyboardButton(text="◀️ Назад")],
    ], resize_keyboard=True)
    await message.answer("Выберите, что хотите изменить:", reply_markup=kb)
    await state.set_state(AccountSettingsStates.choosing_field)


# ----- РЕДАКТИРОВАНИЕ РЕЗЮМЕ -----
@router.message(AccountSettingsStates.choosing_field, F.text == "📄 Текст резюме")
async def edit_resume_start(message: types.Message, state: FSMContext):
    await message.answer("Отправьте новый текст вашего резюме:", reply_markup=ForceReply())
    await state.set_state(AccountSettingsStates.waiting_resume)


@router.message(AccountSettingsStates.waiting_resume, F.text)
async def edit_resume_save(message: types.Message, state: FSMContext):
    new_resume = message.text.strip()
    if not new_resume:
        await message.answer("❌ Текст не может быть пустым.")
        return

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, message.from_user.id)
        if account:
            account.resume_text = new_resume
            await session.commit()
            await message.answer("✅ Текст резюме обновлён!")
        else:
            await message.answer("❌ Аккаунт не найден.")

    # Возвращаемся в меню настроек
    await show_settings_menu(message, state)


# ----- РЕДАКТИРОВАНИЕ ФИЛЬТРА ПОИСКА -----
@router.message(AccountSettingsStates.choosing_field, F.text == "🔎 Фильтр поиска (URL)")
async def edit_filter_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите URL фильтра поиска вакансий (например, https://hh.ru/search/vacancy?text=Python):",
        reply_markup=ForceReply()
    )
    await state.set_state(AccountSettingsStates.waiting_filter)


@router.message(AccountSettingsStates.waiting_filter, F.text)
async def edit_filter_save(message: types.Message, state: FSMContext):
    new_url = message.text.strip()
    if not new_url.startswith(('http://', 'https://')):
        await message.answer("❌ Введите корректный URL, начинающийся с http:// или https://")
        return

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, message.from_user.id)
        if account:
            # Обновляем search_filter (словарь). Сохраняем URL, остальные поля (например, max_pages) оставляем как есть
            current_filter = account.search_filter or {}
            current_filter["url"] = new_url
            account.search_filter = current_filter
            await session.commit()
            await message.answer("✅ URL фильтра обновлён!")
        else:
            await message.answer("❌ Аккаунт не найден.")

    await show_settings_menu(message, state)


# ----- РЕДАКТИРОВАНИЕ ПРОКСИ -----
@router.message(AccountSettingsStates.choosing_field, F.text == "🌐 Прокси")
async def edit_proxy_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите новый прокси (например, http://user:pass@host:port) или '-' для удаления прокси:",
        reply_markup=ForceReply()
    )
    await state.set_state(AccountSettingsStates.waiting_proxy)


@router.message(AccountSettingsStates.waiting_proxy, F.text)
async def edit_proxy_save(message: types.Message, state: FSMContext):
    new_proxy = message.text.strip()
    if new_proxy == "-":
        new_proxy = None
    # Здесь можно добавить валидацию формата прокси, если нужно, но пока оставим как есть

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, message.from_user.id)
        if account:
            account.proxy = new_proxy
            await session.commit()
            await message.answer("✅ Прокси обновлён!" if new_proxy else "✅ Прокси удалён.")
        else:
            await message.answer("❌ Аккаунт не найден.")

    await show_settings_menu(message, state)


@router.message(AccountSettingsStates.choosing_field, F.text == "🔑 Логин/пароль hh")
async def edit_username_start(message: types.Message, state: FSMContext):
    await message.answer("Введите новый логин (email или телефон):", reply_markup=ForceReply())
    await state.set_state(AccountSettingsStates.waiting_username)


@router.message(AccountSettingsStates.waiting_username)
async def edit_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Введите новый пароль:", reply_markup=ForceReply())
    await state.set_state(AccountSettingsStates.waiting_password)


@router.message(AccountSettingsStates.waiting_password)
async def edit_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = data['username']
    password = message.text
    encrypted = encrypt_password(password)
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, message.from_user.id)
        if account:
            account.username = username
            account.password_encrypted = encrypted
            account.cookies = {}  # сбрасываем сессию
            await session.commit()
            await message.answer("✅ Данные обновлены!", reply_markup=get_main_keyboard())
        else:
            await message.answer("❌ Аккаунт не найден.")
    await state.clear()


@router.message(AccountSettingsStates.choosing_field, F.text == "⏱ Лимиты и интервалы")
async def edit_limits_start(message: types.Message, state: FSMContext):
    await message.answer("Введите **минимальный** дневной лимит откликов (целое число):", reply_markup=ForceReply())
    await state.set_state(AccountSettingsStates.waiting_limit_min)


@router.message(AccountSettingsStates.waiting_limit_min, F.text)
async def edit_limit_min(message: types.Message, state: FSMContext):
    try:
        limit_min = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if limit_min <= 0:
        await message.answer("❌ Лимит должен быть положительным.")
        return
    await state.update_data(limit_min=limit_min)
    await message.answer("Введите **максимальный** дневной лимит откликов (целое число):", reply_markup=ForceReply())
    await state.set_state(AccountSettingsStates.waiting_limit_max)


@router.message(AccountSettingsStates.waiting_limit_max, F.text)
async def edit_limit_max(message: types.Message, state: FSMContext):
    try:
        limit_max = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if limit_max <= 0:
        await message.answer("❌ Лимит должен быть положительным.")
        return
    data = await state.get_data()
    limit_min = data.get("limit_min")
    if limit_min > limit_max:
        await message.answer("❌ Максимальный лимит не может быть меньше минимального.")
        return

    # Сохраняем лимиты в БД
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, message.from_user.id)
        if account:
            account.daily_limit_min = limit_min
            account.daily_limit_max = limit_max
            await session.commit()

    # Переходим к вводу интервалов
    await message.answer("✅ Лимиты сохранены. Теперь введите **минимальный** интервал между откликами (в секундах):",
                         reply_markup=ForceReply())
    await state.update_data(limit_min=None, limit_max=None)  # очищаем временные данные
    await state.set_state(AccountSettingsStates.waiting_interval_min)


@router.message(AccountSettingsStates.waiting_interval_min, F.text)
async def edit_interval_min(message: types.Message, state: FSMContext):
    try:
        interval_min = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if interval_min <= 0:
        await message.answer("❌ Интервал должен быть положительным.")
        return
    await state.update_data(interval_min=interval_min)
    await message.answer("Введите **максимальный** интервал между откликами (в секундах):", reply_markup=ForceReply())
    await state.set_state(AccountSettingsStates.waiting_interval_max)


@router.message(AccountSettingsStates.waiting_interval_max, F.text)
async def edit_interval_max(message: types.Message, state: FSMContext):
    try:
        interval_max = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if interval_max <= 0:
        await message.answer("❌ Интервал должен быть положительным.")
        return
    data = await state.get_data()
    interval_min = data.get("interval_min")
    if interval_min > interval_max:
        await message.answer("❌ Максимальный интервал не может быть меньше минимального.")
        return

    # Сохраняем интервалы в БД
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, message.from_user.id)
        if account:
            account.response_interval_min = interval_min
            account.response_interval_max = interval_max
            await session.commit()

    await message.answer("✅ Интервалы сохранены.")
    # Возвращаемся в меню настроек
    await show_settings_menu(message, state)


@router.message(AccountSettingsStates.choosing_field, F.text == "🕒 Рабочее время")
async def edit_work_hours_start(message: types.Message, state: FSMContext):
    await message.answer("Введите час **начала** работы (от 0 до 23):", reply_markup=ForceReply())
    await state.set_state(AccountSettingsStates.waiting_work_start)


@router.message(AccountSettingsStates.waiting_work_start, F.text)
async def edit_work_start(message: types.Message, state: FSMContext):
    try:
        start = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if not (0 <= start < 24):
        await message.answer("❌ Час должен быть от 0 до 23.")
        return
    await state.update_data(work_start=start)
    await message.answer("Введите час **окончания** работы (от 0 до 24, например 17):", reply_markup=ForceReply())
    await state.set_state(AccountSettingsStates.waiting_work_end)


@router.message(AccountSettingsStates.waiting_work_end, F.text)
async def edit_work_end(message: types.Message, state: FSMContext):
    try:
        end = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if not (0 <= end <= 24):
        await message.answer("❌ Час должен быть от 0 до 24.")
        return
    data = await state.get_data()
    start = data.get("work_start")
    if start >= end:
        await message.answer("❌ Час окончания должен быть больше часа начала.")
        return

    # Сохраняем в БД
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, message.from_user.id)
        if account:
            account.work_start_hour = start
            account.work_end_hour = end
            await session.commit()

    await message.answer("✅ Рабочие часы сохранены.")
    # Возвращаемся в меню настроек
    await show_settings_menu(message, state)


# Аналогично для других полей:
# - резюме (waiting_resume)
# - фильтр (waiting_filter) – ожидаем URL, сохраняем в account.search_filter (JSON)
# - прокси (waiting_proxy) – строка

@router.message(AccountSettingsStates.choosing_field, F.text == "◀️ Назад")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())


@router.message(Command("set_resume"))
async def set_resume_start(message: types.Message):
    await message.answer("Отправьте текст вашего резюме (можно скопировать из hh)")


@router.message(F.text & ~F.command)
async def set_resume_text(message: types.Message):
    telegram_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, telegram_id)
        if account:
            account.resume_text = message.text
            await session.commit()
            await message.answer("Резюме сохранено!")
        else:
            await message.answer("Аккаунт не найден. Сначала создайте аккаунт через админ-панель.")


@router.message(Command("parse_now"))
async def parse_now(message: types.Message):
    telegram_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, telegram_id)
        if not account:
            await message.answer("Аккаунт не найден.")
            return
        from app.worker.tasks import parse_new_vacancies_for_account
        parse_new_vacancies_for_account.delay(account.id)
        await message.answer("Задача парсинга запущена в фоне")
