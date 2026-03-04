import asyncio
from aiogram import types, F, Router
from aiogram.types import ForceReply
from sqlalchemy import select

from app.database.models import AsyncSessionLocal, Account, Vacancy
from app.services.hh_parser import HHParser
from app.services.vacancy_filter import extract_secret_word, is_backend_python_keywords
from app.services.letter_generator import generate_cover_letter
from app.utils.proxy_rotator import get_proxy_for_account
from app.keyboards.reply import get_main_keyboard

router = Router()

@router.message(F.text == "🔍 Парсинг вакансий по фильтру")
async def parse_vacancies(message: types.Message):
    telegram_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, telegram_id)
        if not account:
            await message.answer("Аккаунт не найден.")
            return

    # Запускаем задачу Celery
    from app.worker.tasks import parse_new_vacancies_for_account
    parse_new_vacancies_for_account.delay(account.id)
    await message.answer(
        "⏳ Запущен парсинг вакансий по вашему фильтру. Это может занять некоторое время.",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "📝 Парсинг вакансии и генерация сопроводительного")
async def ask_vacancy_link(message: types.Message):
    await message.answer(
        "🔎 Введите ссылку на вакансию (например, https://hh.ru/vacancy/123456):",
        reply_markup=ForceReply(selective=True)
    )

@router.message(F.reply_to_message & F.text)
async def handle_vacancy_link(message: types.Message):
    vacancy_url = message.text.strip()
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        account = await session.get(Account, telegram_id)
        if not account:
            await message.answer("Аккаунт не найден.")
            return

    # Проверяем, что ссылка содержит /vacancy/
    if "/vacancy/" not in vacancy_url:
        await message.answer("❌ Некорректная ссылка на вакансию.")
        return

    # Извлекаем ID вакансии
    try:
        hh_id = vacancy_url.split("/vacancy/")[1].split("?")[0]
    except IndexError:
        await message.answer("❌ Не удалось распознать ID вакансии.")
        return

    # Проверяем, есть ли уже такая вакансия в БД
    async with AsyncSessionLocal() as session:
        existing_vacancy = await session.execute(
            select(Vacancy).where(Vacancy.hh_id == hh_id)
        )
        vacancy = existing_vacancy.scalar_one_or_none()

    if not vacancy:
        # Парсим вакансию
        proxy = get_proxy_for_account(account.id)
        parser = HHParser(account_id=account.id, proxy=proxy)
        try:
            details = await parser.parse_vacancy_details(vacancy_url)
            if "error" in details:
                await message.answer(f"❌ Ошибка парсинга: {details['error']}")
                return
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
            return

        # Фильтрация (опционально)
        if not is_backend_python_keywords("", details.get("description", "")):
            await message.answer("⚠️ Вакансия не похожа на backend Python. Всё равно сгенерировать письмо?", reply_markup=ForceReply())
            # Здесь можно добавить подтверждение, но для простоты продолжим

        # Сохраняем вакансию
        async with AsyncSessionLocal() as session:
            vacancy = Vacancy(
                hh_id=hh_id,
                title=details.get("title", "Без названия"),
                url=vacancy_url,
                description=details.get("description", ""),
                check_word=extract_secret_word(details.get("description", ""))
            )
            session.add(vacancy)
            await session.commit()
            await session.refresh(vacancy)
    else:
        # Вакансия уже есть, используем её
        pass

    # Генерируем письмо
    try:
        letter = await generate_cover_letter(
            vacancy_title=vacancy.title,
            vacancy_description=vacancy.description,
            company="Компания",  # Можно парсить отдельно
            resume_text=account.resume_text,
            secret_word=vacancy.check_word
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка генерации письма: {e}")
        return

    # Отправляем результат
    await message.answer(
        f"📄 **Вакансия:** {vacancy.title}\n"
        f"🔗 {vacancy.url}\n\n"
        f"**Сгенерированное сопроводительное:**\n\n{letter}",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )