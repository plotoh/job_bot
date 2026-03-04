import logging
from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.fsm.states import UserTestStates
from app.services.account import get_account
from app.keyboards.reply import get_main_keyboard
from app.worker.tasks import run_test_for_account

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "🧪 Тестовый режим")
async def test_mode_entry(message: types.Message, state: FSMContext):
    account = await get_account(message.from_user.id)
    if not account:
        await message.answer("У вас нет привязанного аккаунта. Обратитесь к администратору.")
        return
    await show_test_menu(message, account, state)


async def show_test_menu(update: types.Message | CallbackQuery, account, state: FSMContext):
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
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="test_back")],
    ])

    text = (
        f"🧪 **Тестовый режим для аккаунта {account.username}**\n\n"
        "Вы можете настроить, какие этапы будут выполняться при тестовом отклике.\n"
        "После запуска бот отправит отчёт о результатах."
    )

    if isinstance(update, types.Message):
        await update.answer(text, reply_markup=kb, parse_mode="Markdown")
    elif isinstance(update, CallbackQuery):
        await update.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(UserTestStates.main_menu)
    await state.update_data(account_id=account.id)


@router.callback_query(StateFilter(UserTestStates.main_menu), F.data.startswith("test_toggle_"))
async def toggle_test_flag(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    field = callback.data.split("_")[2]  # parse, generate, send

    from app.database.models import AsyncSessionLocal, Account
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if field == "parse":
            account.test_parse_vacancy = not account.test_parse_vacancy
        elif field == "generate":
            account.test_generate_letter = not account.test_generate_letter
        elif field == "send":
            account.test_send_response = not account.test_send_response
        await session.commit()
        await session.refresh(account)

    await show_test_menu(callback, account, state)
    await callback.answer()


@router.callback_query(StateFilter(UserTestStates.main_menu), F.data == "test_set_count")
async def set_test_count(callback: CallbackQuery, state: FSMContext):
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

    from app.database.models import AsyncSessionLocal, Account
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        account.test_count = count
        await session.commit()
        await session.refresh(account)

    await message.delete()
    await show_test_menu(message, account, state)


@router.callback_query(StateFilter(UserTestStates.main_menu), F.data == "test_run")
async def run_test(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    chat_id = callback.from_user.id
    count = (await get_account(account_id)).test_count  # получаем количество

    await callback.message.edit_text("🚀 Запускаю тестовую генерацию... Это может занять некоторое время.")
    from app.worker.tasks import run_test_generation
    run_test_generation.delay(account_id, chat_id, count)
    await state.clear()
    await callback.answer("Тест запущен. Результат придёт в этот чат.")

# @router.callback_query(StateFilter(UserTestStates.main_menu), F.data == "test_run")
# async def run_test(callback: CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     account_id = data["account_id"]
#     chat_id = callback.from_user.id
#
#     await callback.message.edit_text("🚀 Запускаю тестовые отклики... Это может занять некоторое время.")
#     run_test_for_account.delay(account_id, chat_id)
#     await state.clear()
#     await callback.answer("Тест запущен. Результат придёт в этот чат.")


@router.callback_query(F.data == "test_back")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard(callback.from_user.id))
    await callback.answer()
