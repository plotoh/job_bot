import logging
from aiogram import types, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.config import settings
from app.fsm.states import AdminAddAccountStates
from app.services.account import create_account, get_account
from app.utils.encryption import encrypt_password
from .main import admin_main_menu, is_admin

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_add_account")
async def admin_add_account_callback(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} clicked add account")
    await callback.message.edit_text("Введите telegram ID пользователя (целое число):")
    await state.set_state(AdminAddAccountStates.waiting_telegram_id)
    await callback.answer()


@router.message(Command("add_account"), is_admin)
async def add_account_start(message: types.Message, state: FSMContext):
    logger.info(f"Admin {message.from_user.id} started add_account via command")
    await message.answer("Введите telegram ID пользователя (целое число):")
    await state.set_state(AdminAddAccountStates.waiting_telegram_id)


@router.message(StateFilter(AdminAddAccountStates.waiting_telegram_id), F.text)
async def add_account_telegram_id(message: types.Message, state: FSMContext):
    try:
        telegram_id = int(message.text)
    except ValueError:
        logger.warning(f"Admin {message.from_user.id} entered invalid telegram_id: {message.text}")
        await message.answer("❌ Введите целое число.")
        return

    existing = await get_account(telegram_id)
    if existing:
        logger.warning(f"Admin {message.from_user.id} tried to add existing account {telegram_id}")
        await message.answer("❌ Аккаунт с таким telegram ID уже существует.")
        return
    await state.update_data(account_id=telegram_id)
    await message.answer("Введите username (логин на hh.ru):")
    await state.set_state(AdminAddAccountStates.waiting_username)


@router.message(StateFilter(AdminAddAccountStates.waiting_username), F.text)
async def add_account_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Введите пароль (будет зашифрован):")
    await state.set_state(AdminAddAccountStates.waiting_password)


@router.message(StateFilter(AdminAddAccountStates.waiting_password), F.text)
async def add_account_password(message: types.Message, state: FSMContext):
    encrypted = encrypt_password(message.text)
    await state.update_data(password_encrypted=encrypted)
    await message.answer("Введите resume_id (ID резюме на hh.ru):")
    await state.set_state(AdminAddAccountStates.waiting_resume_id)


@router.message(StateFilter(AdminAddAccountStates.waiting_resume_id), F.text)
async def add_account_resume_id(message: types.Message, state: FSMContext):
    await state.update_data(resume_id=message.text)
    await message.answer("Введите прокси (или '-' если не нужно):")
    await state.set_state(AdminAddAccountStates.waiting_proxy)


@router.message(StateFilter(AdminAddAccountStates.waiting_proxy), F.text)
async def add_account_proxy(message: types.Message, state: FSMContext):
    proxy = message.text.strip()
    if proxy == "-":
        proxy = None
    await state.update_data(proxy=proxy)
    await message.answer("Введите URL фильтра поиска вакансий (например, https://hh.ru/search/vacancy?text=Python):")
    await state.set_state(AdminAddAccountStates.waiting_filter_url)


@router.message(StateFilter(AdminAddAccountStates.waiting_filter_url), F.text)
async def add_account_filter_url(message: types.Message, state: FSMContext):
    await state.update_data(filter_url=message.text)
    await message.answer("Введите максимальное количество страниц для парсинга (целое число):")
    await state.set_state(AdminAddAccountStates.waiting_filter_pages)


@router.message(StateFilter(AdminAddAccountStates.waiting_filter_pages), F.text)
async def add_account_filter_pages(message: types.Message, state: FSMContext):
    try:
        pages = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return

    data = await state.get_data()
    data['max_pages'] = pages
    success = await create_account(data)
    if success:
        logger.info(f"Admin {message.from_user.id} created account for user {data['account_id']}")
        await message.answer("✅ Аккаунт успешно создан!")
    else:
        await message.answer("❌ Ошибка при создании аккаунта.")
    await state.clear()
    await admin_main_menu(message, state)
