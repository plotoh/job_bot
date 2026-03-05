# app/handlers/vacancy.py
import logging
import re
from aiogram import types, F, Router
from aiogram.types import ForceReply
from sqlalchemy import select

from app.config import settings
from app.database.models import AsyncSessionLocal, Account, Vacancy
from app.services.vacancy_parser import HHDetailParser
from app.services.vacancy_filter import extract_secret_word, is_backend_python_keywords
from app.services.letter_generator import generate_cover_letter
from app.utils.proxy_rotator import get_proxy_for_account
from app.utils.encryption import decrypt_password
from app.services.login import login_and_get_cookies
from app.keyboards.reply import get_main_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "🔍 Парсинг вакансий по фильтру")
async def parse_vacancies(message: types.Message):
    user_id = message.from_user.id

    # Если это администратор
    if user_id == settings.ADMIN_ID:
        # Берём первый активный аккаунт из БД
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Account).limit(1))
            account = result.scalar_one_or_none()
        if not account:
            await message.answer("❌ Нет ни одного аккаунта для парсинга.")
            return

        from app.worker.tasks import parse_new_vacancies_for_account
        parse_new_vacancies_for_account.delay(account.id)
        await message.answer(
            f"⏳ Запущен парсинг вакансий для аккаунта {account.username}. Это может занять некоторое время.",
            reply_markup=get_main_keyboard(user_id)
        )
        return

    # Для обычного пользователя
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, user_id)
        if not account:
            await message.answer("Аккаунт не найден.")
            return

    from app.worker.tasks import parse_new_vacancies_for_account
    parse_new_vacancies_for_account.delay(account.id)
    await message.answer(
        "⏳ Запущен парсинг вакансий по вашему фильтру. Это может занять некоторое время.",
        reply_markup=get_main_keyboard(user_id)
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

    if "/vacancy/" not in vacancy_url:
        await message.answer("❌ Некорректная ссылка на вакансию.")
        return

    try:
        hh_id = vacancy_url.split("/vacancy/")[1].split("?")[0]
    except IndexError:
        await message.answer("❌ Не удалось распознать ID вакансии.")
        return

    async with AsyncSessionLocal() as session:
        existing_vacancy = await session.execute(
            select(Vacancy).where(Vacancy.hh_id == hh_id)
        )
        vacancy = existing_vacancy.scalar_one_or_none()

    if not vacancy:
        # Получаем cookies аккаунта
        cookies = account.cookies or {}
        if not cookies:
            try:
                password = decrypt_password(account.password_encrypted)
                cookies = await login_and_get_cookies(account.username, password)
                async with AsyncSessionLocal() as session:
                    acc = await session.get(Account, account.id)
                    acc.cookies = cookies
                    await session.commit()
            except Exception as e:
                logger.error(f"Login failed for account {account.id}: {e}")
                await message.answer("❌ Не удалось авторизоваться на hh.ru. Проверьте логин/пароль.")
                return

        parser = HHDetailParser(cookies=cookies, proxy=get_proxy_for_account(account.id))
        try:
            details = await parser.parse(int(hh_id))
            if "error" in details:
                await message.answer(f"❌ Ошибка парсинга: {details['error']}")
                return
        except Exception as e:
            logger.error(f"Error parsing vacancy {hh_id}: {e}", exc_info=True)
            await message.answer(f"❌ Ошибка: {e}")
            return

        # Извлекаем название вакансии из HTML
        title_match = re.search(r'<h1[^>]*data-qa="vacancy-title"[^>]*>(.*?)</h1>', details.get("full_html", ""),
                                re.DOTALL)
        title = title_match.group(1).strip() if title_match else "Без названия"

        # Проверка по ключевым словам
        if not is_backend_python_keywords(title, details.get("description", "")):
            await message.answer("⚠️ Вакансия не похожа на backend Python. Всё равно сгенерировать письмо?",
                                 reply_markup=ForceReply())

        # Сохраняем вакансию в БД
        async with AsyncSessionLocal() as session:
            vacancy = Vacancy(
                hh_id=hh_id,
                title=title,
                url=vacancy_url,
                description=details.get("description", ""),
                check_word=extract_secret_word(details.get("description", ""))
            )
            session.add(vacancy)
            await session.commit()
            await session.refresh(vacancy)

    # Генерируем письмо
    try:
        letter = await generate_cover_letter(
            vacancy_title=vacancy.title,
            vacancy_description=vacancy.description,
            company="",
            resume_text=account.resume_text,
            secret_word=vacancy.check_word,
            tg_username=account.telegram_username
        )
    except Exception as e:
        logger.error(f"Error generating letter: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка генерации письма: {e}")
        return

    await message.answer(
        f"📄 **Вакансия:** {vacancy.title}\n"
        f"🔗 {vacancy.url}\n\n"
        f"**Сгенерированное сопроводительное:**\n\n{letter}",
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )
