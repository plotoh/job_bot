from aiogram import types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ForceReply
from aiogram.fsm.state import State, StatesGroup
from aiogram import Router

from app.database.models import AsyncSessionLocal, Account
from app.keyboards.reply import get_main_keyboard
from app.utils.encryption import encrypt_password
from app.services.account_data import format_account_text

router = Router()


class AccountSettingsStates(StatesGroup):
    choosing_field = State()
    waiting_username = State()
    waiting_password = State()
    waiting_proxy = State()
    waiting_resume = State()
    waiting_filter = State()
    # Убраны состояния для лимитов и интервалов, так как пользователь их не меняет
    # waiting_limit_min, waiting_limit_max, waiting_interval_min, waiting_interval_max, waiting_work_start, waiting_work_end


async def show_settings_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔑 Логин/пароль hh")],
        [KeyboardButton(text="📄 Текст резюме")],
        [KeyboardButton(text="🔎 Фильтр поиска (URL)")],
        [KeyboardButton(text="🌐 Прокси")],
        [KeyboardButton(text="◀️ Назад")],
    ], resize_keyboard=True)
    await message.answer("Выберите, что хотите изменить:", reply_markup=kb)
    await state.set_state(AccountSettingsStates.choosing_field)


@router.message(F.text == "⚙️ Настройки аккаунта")
async def account_settings_menu(message: types.Message, state: FSMContext):
    await show_settings_menu(message, state)


# ----- Новая кнопка "📋 Все данные" -----
@router.message(F.text == "📋 Все данные")
async def show_all_data(message: types.Message):
    telegram_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, telegram_id)
        if not account:
            await message.answer("У вас нет привязанного аккаунта.", reply_markup=get_main_keyboard(message.from_user.id))
            return
        text = format_account_text(account)
    await message.answer(text, reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")


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

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, message.from_user.id)
        if account:
            account.proxy = new_proxy
            # Сбрасываем cookies при смене прокси (как в admin)
            account.cookies = {}
            await session.commit()
            await message.answer("✅ Прокси обновлён!" if new_proxy else "✅ Прокси удалён.")
        else:
            await message.answer("❌ Аккаунт не найден.")

    await show_settings_menu(message, state)


# ----- РЕДАКТИРОВАНИЕ ЛОГИНА/ПАРОЛЯ -----
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
            await message.answer("✅ Данные обновлены!", reply_markup=get_main_keyboard(message.from_user.id))
        else:
            await message.answer("❌ Аккаунт не найден.")
    await state.clear()


# ----- Кнопка "Назад" -----
@router.message(AccountSettingsStates.choosing_field, F.text == "◀️ Назад")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))


# ----- Остальные старые хэндлеры (set_resume, parse_now) можно оставить -----
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
