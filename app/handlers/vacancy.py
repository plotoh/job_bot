import asyncio
from aiogram import types, F
from aiogram import Router
from aiogram.types import ForceReply

from app.keyboards.reply import get_main_keyboard

router = Router()


@router.message(F.text == "🔍 Парсинг вакансий по фильтру")
async def parse_vacancies(message: types.Message):
    await message.answer(
        "⏳ Запускаю парсинг вакансий по вашему фильтру...",
        reply_markup=get_main_keyboard()
    )
    await asyncio.sleep(2)
    await message.answer(
        "✅ Парсинг завершён! Найдено 15 новых вакансий.",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "📝 Парсинг вакансии и генерация сопроводительного")
async def ask_vacancy_link(message: types.Message):
    await message.answer(
        "🔎 Введите ссылку на вакансию или её ID:",
        reply_markup=ForceReply(selective=True)
    )


@router.message(F.reply_to_message & F.text)
async def handle_vacancy_link(message: types.Message):
    vacancy_input = message.text
    await message.answer(
        f"📄 Вакансия по ссылке: {vacancy_input}\n"
        "Навыки: Python, Django, SQL\n"
        "Сгенерированное сопроводительное:\n\n"
        "Здравствуйте! Меня заинтересовала ваша вакансия. "
        f"```Имею опыт коммерческой разработки на Python 3+ года...```",
        reply_markup=get_main_keyboard()
    )
