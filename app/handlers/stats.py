from aiogram import types, F
from aiogram import Router

from app.keyboards.reply import get_main_keyboard

router = Router()

@router.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    await message.answer(
        "📈 Статистика (демо):\n"
        "Откликов сегодня: 5\n"
        "Всего откликов: 127\n"
        "Приглашений на собеседование: 8",
        reply_markup=get_main_keyboard()
    )