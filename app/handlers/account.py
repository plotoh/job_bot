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


# Аналогично для других полей:
# - резюме (waiting_resume)
# - фильтр (waiting_filter) – ожидаем URL, сохраняем в account.search_filter (JSON)
# - прокси (waiting_proxy) – строка
# - лимиты и интервалы – можно сделать последовательный ввод
# - рабочее время – два числа (часы)

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
