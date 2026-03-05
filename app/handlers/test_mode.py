import logging
from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.fsm.states import UserTestStates
from app.services.account_crud import get_account, update_test_flags, update_test_count
from app.worker.tasks import run_test_for_account
from app.keyboards.reply import get_main_keyboard

logger = logging.getLogger(__name__)
router = Router()


async def show_test_menu(update: types.Message | CallbackQuery, account, state: FSMContext, is_admin: bool = False):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅' if account.test_parse_vacancy else '❌'} Парсить вакансию",
            callback_data="test_toggle_parse"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if account.test_generate_letter else '❌'} Генерировать письмо",
            callback_data="test_toggle_generate"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if account.test_send_response else '❌'} Отправлять отклик",
            callback_data="test_toggle_send"
        )],
        [InlineKeyboardButton(
            text=f"🔢 Количество: {account.test_count}",
            callback_data="test_set_count"
        )],
        [InlineKeyboardButton(text="🚀 Запустить тест", callback_data="test_run")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="test_back")],
    ])
    text = f"🧪 **Тестовый режим для аккаунта {account.username}**\n\nНастройте параметры."
    if isinstance(update, types.Message):
        await update.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await state.update_data(account_id=account.id, is_admin=is_admin)
    await state.set_state(UserTestStates.main_menu)


@router.message(F.text == "🧪 Тестовый режим")
async def test_mode_entry(message: types.Message, state: FSMContext):
    account = await get_account(message.from_user.id)
    if not account:
        await message.answer("У вас нет привязанного аккаунта. Обратитесь к администратору.")
        return
    await show_test_menu(message, account, state, is_admin=False)


@router.callback_query(StateFilter(UserTestStates.main_menu), F.data.startswith("test_toggle_"))
async def toggle_test_flag(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    flag = callback.data.split("_")[2]  # parse, generate, send
    await update_test_flags(account_id, flag)
    account = await get_account(account_id)
    await show_test_menu(callback, account, state, data.get("is_admin", False))
    await callback.answer()


@router.callback_query(StateFilter(UserTestStates.main_menu), F.data == "test_set_count")
async def set_test_count_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите количество тестовых откликов (целое число):")
    await state.set_state(UserTestStates.waiting_count)
    await callback.answer()


@router.message(StateFilter(UserTestStates.waiting_count), F.text)
async def receive_test_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if count <= 0:
        await message.answer("❌ Число должно быть положительным.")
        return
    data = await state.get_data()
    account_id = data["account_id"]
    await update_test_count(account_id, count)
    account = await get_account(account_id)
    await message.delete()
    await show_test_menu(message, account, state, data.get("is_admin", False))


@router.callback_query(StateFilter(UserTestStates.main_menu), F.data == "test_run")
async def run_test(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    chat_id = callback.from_user.id
    await callback.message.edit_text("🚀 Запускаю тестовую генерацию... Это может занять некоторое время.")
    run_test_for_account.delay(account_id, chat_id)
    await state.clear()
    await callback.answer("Тест запущен. Результат придёт в этот чат.")


@router.callback_query(F.data == "test_back")
async def back_from_test(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    is_admin = data.get("is_admin", False)
    if is_admin:
        await callback.message.delete()
        from .admin.main import admin_main_menu   # <-- изменено
        await admin_main_menu(callback.message, state)
    else:
        await state.clear()
        await callback.message.delete()
        await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()
