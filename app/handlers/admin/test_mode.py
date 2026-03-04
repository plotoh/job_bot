import logging
from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.database.models import Account
from app.fsm.states import AdminEditStates
from app.services.account import get_account
from app.config import settings
from app.worker.tasks import run_test_for_account

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(AdminEditStates.choosing_action, F.data == "admin_test_mode")
async def test_mode_menu(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} opened test mode for account")
    data = await state.get_data()
    account_id = data["account_id"]
    account = await get_account(account_id)
    if not account:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return

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
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_account")],
    ])
    await callback.message.edit_text("Настройки тестового режима:", reply_markup=kb)
    await state.set_state("test_mode")
    await callback.answer()


@router.callback_query(F.data.startswith("test_toggle_"))
async def test_toggle(callback: CallbackQuery, state: FSMContext):
    data_state = await state.get_data()
    account_id = data_state["account_id"]
    field = callback.data.split("_")[2]  # parse, generate, send

    account = await get_account(account_id)
    if not account:
        await callback.answer("Аккаунт не найден", show_alert=True)
        return

    async with account._sessionmaker() as session:  # но проще через сервис обновления
        # Для обновления тестовых флагов нужно добавить функцию в account_service
        # Пока оставим прямой доступ к БД (или создадим сервис)
        from app.database.models import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            account_db = await session.get(Account, account_id)
            if field == "parse":
                account_db.test_parse_vacancy = not account_db.test_parse_vacancy
            elif field == "generate":
                account_db.test_generate_letter = not account_db.test_generate_letter
            elif field == "send":
                account_db.test_send_response = not account_db.test_send_response
            await session.commit()
            logger.info(f"Admin {callback.from_user.id} toggled test flag {field} for account {account_id}")

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
    data_state = await state.get_data()
    account_id = data_state["account_id"]

    from app.database.models import AsyncSessionLocal, Account
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, account_id)
        if account:
            account.test_count = count
            await session.commit()
            logger.info(f"Admin {message.from_user.id} set test count to {count} for account {account_id}")

    await message.answer("✅ Количество сохранено.")
    await message.delete()
    # Возвращаемся в меню тестового режима
    # Для этого нужно вызвать test_mode_menu, но нужен callback
    # Создадим искусственный callback
    from aiogram.types import CallbackQuery
    # Проще: показать меню заново через отправку нового сообщения
    account = await get_account(account_id)
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
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_account")],
    ])
    await message.answer("Настройки тестового режима:", reply_markup=kb)


@router.callback_query(F.data == "test_run")
async def admin_run_test(callback: CallbackQuery, state: FSMContext):
    data_state = await state.get_data()
    account_id = data_state["account_id"]
    chat_id = callback.from_user.id
    run_test_for_account.delay(account_id, chat_id)
    logger.info(f"Admin {callback.from_user.id} started test for account {account_id}")
    await callback.answer("Тест запущен, результат придёт сюда")
    await callback.message.edit_text("✅ Тест запущен. Ожидайте результат...")
