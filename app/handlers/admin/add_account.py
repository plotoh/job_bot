import logging
from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database.models import AsyncSessionLocal, Account
from app.fsm.states import AdminAddAccountStates
from app.services.account_crud import create_account
from app.utils.encryption import encrypt_password
from app.handlers.admin.main import admin_main_menu

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_add_account")
async def add_account_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите telegram ID пользователя (целое число):")
    await state.set_state(AdminAddAccountStates.waiting_telegram_id)
    await callback.answer()


@router.message(AdminAddAccountStates.waiting_telegram_id, F.text)
async def add_account_telegram_id(message: Message, state: FSMContext):
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
async def add_account_username(message: Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Введите пароль (будет зашифрован):")
    await state.set_state(AdminAddAccountStates.waiting_password)


@router.message(AdminAddAccountStates.waiting_password, F.text)
async def add_account_password(message: Message, state: FSMContext):
    encrypted = encrypt_password(message.text)
    await state.update_data(password_encrypted=encrypted)
    await message.answer("Введите resume_id (ID резюме на hh.ru):")
    await state.set_state(AdminAddAccountStates.waiting_resume_id)


@router.message(AdminAddAccountStates.waiting_resume_id, F.text)
async def add_account_resume_id(message: Message, state: FSMContext):
    await state.update_data(resume_id=message.text)
    await message.answer("Введите прокси (или '-' если не нужно):")
    await state.set_state(AdminAddAccountStates.waiting_proxy)


@router.message(AdminAddAccountStates.waiting_proxy, F.text)
async def add_account_proxy(message: Message, state: FSMContext):
    proxy = message.text.strip()
    if proxy == "-":
        proxy = None
    await state.update_data(proxy=proxy)
    await message.answer("Введите URL фильтра поиска вакансий (например, https://hh.ru/search/vacancy?text=Python):")
    await state.set_state(AdminAddAccountStates.waiting_filter_url)


@router.message(AdminAddAccountStates.waiting_filter_url, F.text)
async def add_account_filter_url(message: Message, state: FSMContext):
    await state.update_data(filter_url=message.text)

    data = await state.get_data()
    success = await create_account(data)
    if success:
        await message.answer("✅ Аккаунт успешно создан!")
        logger.info("Admin created account with ID %s", data['account_id'])
    else:
        await message.answer("❌ Ошибка при создании аккаунта.")
    await state.clear()
    await admin_main_menu(message, state)
