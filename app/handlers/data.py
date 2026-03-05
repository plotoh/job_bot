# app/handlers/data.py
from aiogram import types, F, Router
from app.services.account import get_account
from app.services.account_data import format_account_text
from app.keyboards.reply import get_main_keyboard

router = Router()

@router.message(F.text == "📋 Все данные")
async def show_all_data(message: types.Message):
    account = await get_account(message.from_user.id)
    if not account:
        await message.answer("У вас нет привязанного аккаунта.", reply_markup=get_main_keyboard(message.from_user.id))
        return
    text = format_account_text(account)
    await message.answer(text, reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")