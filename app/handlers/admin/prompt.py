import logging
from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from app.fsm.states import AdminEditStates
from app.services.account import get_account, update_account_prompt
from app.services.letter_generator import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(StateFilter(AdminEditStates.choosing_action), F.data == "admin_edit_prompt")
async def edit_prompt_start(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Admin {callback.from_user.id} started editing prompt")
    data = await state.get_data()
    account_id = data["account_id"]
    account = await get_account(account_id)

    # Показываем текущий промпт
    current = account.system_prompt if account.system_prompt else DEFAULT_SYSTEM_PROMPT
    preview = current[:200] + "..." if len(current) > 200 else current

    text = (
        f"🤖 <b>Системный промпт для LLM</b>\n\n"
        f"<b>Текущий промпт:</b>\n<code>{preview}</code>\n\n"
        f"Чтобы изменить, отправьте новый текст промпта (можно скопировать из стандартного).\n"
        f"Для сброса к стандартному введите: <code>/reset</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_to_account")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(AdminEditStates.editing_prompt)
    await callback.answer()

@router.message(StateFilter(AdminEditStates.editing_prompt), F.text)
async def edit_prompt_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    new_prompt = message.text.strip()

    if new_prompt == "/reset":
        new_prompt = ""  # пустая строка означает стандартный

    if await update_account_prompt(account_id, new_prompt):
        logger.info(f"Admin {message.from_user.id} updated prompt for account {account_id}")
        await message.answer("✅ Системный промпт обновлён!")
    else:
        await message.answer("❌ Ошибка обновления.")

    # Возвращаемся в меню аккаунта
    from app.handlers.admin.accounts import account_selected
    # Создаём искусственный callback
    from aiogram.types import CallbackQuery
    # Упростим: покажем главное меню админа
    from app.handlers.admin.main import admin_main_menu
    await admin_main_menu(message, state)