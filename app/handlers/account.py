from aiogram import types, F
from aiogram.filters import Command
from app.database.models import AsyncSessionLocal, Account
from app.utils.encryption import encrypt
from aiogram import Router


router = Router()
@router.message(Command("set_resume"))
async def set_resume_start(message: types.Message):
    await message.answer("Отправьте текст вашего резюме (можно скопировать из hh)")

@router.message(F.text & ~F.command)
async def set_resume_text(message: types.Message):
    # Предположим, что аккаунт уже создан и связан с пользователем
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, 1)  # для примера
        if account:
            account.resume_text = message.text
            await session.commit()
            await message.answer("Резюме сохранено!")


@router.message(Command("parse_now"))
async def parse_now(message: types.Message):
    from app.worker.tasks import parse_new_vacancies_for_account
    parse_new_vacancies_for_account.delay(1)  # для аккаунта с id=1
    await message.answer("Задача парсинга запущена в фоне")