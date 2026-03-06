from aiogram import types, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ForceReply

from app.fsm.states import UserSettingsStates
from app.services import account_crud as crud
from app.services.exceptions import ObjectNotFound
from app.keyboards.reply import get_main_keyboard
from app.handlers.common_edit import start_editing

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


# ----- Поля, редактируемые через общий механизм -----
@router.message(UserSettingsStates.choosing_field, F.text == "📱 Telegram username")
async def edit_telegram_username_start(message: types.Message, state: FSMContext):
    await start_editing(message, state, field='telegram_username', mode='user')


@router.message(UserSettingsStates.choosing_field, F.text == "📄 Текст резюме")
async def edit_resume_start(message: types.Message, state: FSMContext):
    await start_editing(message, state, field='resume', mode='user')


@router.message(UserSettingsStates.choosing_field, F.text == "🔎 Фильтр поиска (URL)")
async def edit_filter_start(message: types.Message, state: FSMContext):
    await start_editing(message, state, field='filter', mode='user')


@router.message(UserSettingsStates.choosing_field, F.text == "🌐 Прокси")
async def edit_proxy_start(message: types.Message, state: FSMContext):
    await start_editing(message, state, field='proxy', mode='user')


# ----- Логин/пароль (два шага) -----
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
    try:
        await crud.update_account_credentials(message.from_user.id, username, password)
        await message.answer("✅ Данные обновлены!", reply_markup=get_main_keyboard(message.from_user.id))
    except ObjectNotFound:
        await message.answer("❌ Аккаунт не найден.")
    await state.clear()


# ----- Назад -----
@router.message(UserSettingsStates.choosing_field, F.text == "◀️ Назад")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_keyboard(message.from_user.id))