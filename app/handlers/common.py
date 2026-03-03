from aiogram import types
from aiogram.filters import Command
from aiogram import Router

from app.keyboards.reply import get_main_keyboard

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот для работы с HeadHunter.\n"
        "Выберите действие на клавиатуре ниже:",
        reply_markup=get_main_keyboard()
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "Доступные команды:\n"
        "/start - показать главное меню\n"
        "/help - эта справка",
        reply_markup=get_main_keyboard()
    )
