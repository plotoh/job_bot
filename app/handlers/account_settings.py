from aiogram import types, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ForceReply

from app.fsm.states import UserSettingsStates
from app.services.account import (
    update_account_telegram_username,
    update_account_credentials,
    update_account_resume,
    update_account_filter,
    update_account_proxy
)
from app.keyboards.reply import get_main_keyboard

router = Router()


async def show_settings_menu(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telegram username")],
            [KeyboardButton(text="🔑 Логин/пароль hh")],
            [KeyboardButton(text="📄 Текст резюме")],
            [KeyboardButton(text="🔎 Фильтр поиска (URL)")],
            [KeyboardButton(text="🌐 Прокси")],
            [KeyboardButton(text="◀️ Назад")],
        ],
        resize_keyboard=True
    )
    await message.answer("Выберите, что хотите изменить:", reply_markup=kb)
    await state.set_state(UserSettingsStates.choosing_field)


@router.message(F.text == "⚙️ Настройки аккаунта")
async def account_settings_menu(message: types.Message, state: FSMContext):
    await show_settings_menu(message, state)


# --- Telegram username ---
@router.message(UserSettingsStates.choosing_field, F.text == "📱 Telegram username")
async def edit_telegram_username_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите ваш Telegram username (например, @username) или отправьте '-' чтобы удалить:",
        reply_markup=ForceReply()
    )
    await state.set_state(UserSettingsStates.waiting_telegram_username)


@router.message(UserSettingsStates.waiting_telegram_username, F.text)
async def edit_telegram_username_save(message: types.Message, state: FSMContext):
    new_username = message.text.strip()
    if new_username == "-":
        new_username = None
    if await update_account_telegram_username(message.from_user.id, new_username):
        await message.answer("✅ Telegram username обновлён!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_settings_menu(message, state)


# --- Логин/пароль ---
@router.message(UserSettingsStates.choosing_field, F.text == "🔑 Логин/пароль hh")
async def edit_username_start(message: types.Message, state: FSMContext):
    await message.answer("Введите новый логин (email или телефон):", reply_markup=ForceReply())
    await state.set_state(UserSettingsStates.waiting_username)


@router.message(UserSettingsStates.waiting_username, F.text)
async def edit_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Введите новый пароль:", reply_markup=ForceReply())
    await state.set_state(UserSettingsStates.waiting_password)


@router.message(UserSettingsStates.waiting_password, F.text)
async def edit_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = data['username']
    password = message.text
    if await update_account_credentials(message.from_user.id, username, password):
        await message.answer("✅ Данные обновлены!", reply_markup=get_main_keyboard(message.from_user.id))
    else:
        await message.answer("❌ Аккаунт не найден.")
    await state.clear()


# --- Резюме ---
@router.message(UserSettingsStates.choosing_field, F.text == "📄 Текст резюме")
async def edit_resume_start(message: types.Message, state: FSMContext):
    await message.answer("Отправьте новый текст вашего резюме:", reply_markup=ForceReply())
    await state.set_state(UserSettingsStates.waiting_resume)


@router.message(UserSettingsStates.waiting_resume, F.text)
async def edit_resume_save(message: types.Message, state: FSMContext):
    new_resume = message.text.strip()
    if not new_resume:
        await message.answer("❌ Текст не может быть пустым.")
        return
    if await update_account_resume(message.from_user.id, new_resume):
        await message.answer("✅ Текст резюме обновлён!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_settings_menu(message, state)


# --- Фильтр ---
@router.message(UserSettingsStates.choosing_field, F.text == "🔎 Фильтр поиска (URL)")
async def edit_filter_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите URL фильтра поиска вакансий (например, https://hh.ru/search/vacancy?text=Python):",
        reply_markup=ForceReply()
    )
    await state.set_state(UserSettingsStates.waiting_filter)


@router.message(UserSettingsStates.waiting_filter, F.text)
async def edit_filter_save(message: types.Message, state: FSMContext):
    new_url = message.text.strip()
    if not new_url.startswith(('http://', 'https://')):
        await message.answer("❌ Введите корректный URL, начинающийся с http:// или https://")
        return
    if await update_account_filter(message.from_user.id, new_url):
        await message.answer("✅ URL фильтра обновлён!")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_settings_menu(message, state)


# --- Прокси ---
@router.message(UserSettingsStates.choosing_field, F.text == "🌐 Прокси")
async def edit_proxy_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите новый прокси (например, http://user:pass@host:port) или '-' для удаления прокси:",
        reply_markup=ForceReply()
    )
    await state.set_state(UserSettingsStates.waiting_proxy)


@router.message(UserSettingsStates.waiting_proxy, F.text)
async def edit_proxy_save(message: types.Message, state: FSMContext):
    new_proxy = message.text.strip()
    if new_proxy == "-":
        new_proxy = None
    if await update_account_proxy(message.from_user.id, new_proxy):
        await message.answer("✅ Прокси обновлён!" if new_proxy else "✅ Прокси удалён.")
    else:
        await message.answer("❌ Аккаунт не найден.")
    await show_settings_menu(message, state)


# --- Назад ---
@router.message(UserSettingsStates.choosing_field, F.text == "◀️ Назад")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))
