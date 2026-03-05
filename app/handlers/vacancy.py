import logging
import re

from aiogram import types, F, Router
from aiogram.types import ForceReply
from sqlalchemy import select

from app.config import settings
from app.database.models import AsyncSessionLocal, Account, Vacancy
from app.keyboards.reply import get_main_keyboard

from app.services.letter_generator import generate_cover_letter
from app.services.vacancy_filter import extract_secret_word
from app.services.vacancy import _ensure_account_vacancy_link  # временно, лучше вынести

from app.utils.encryption import decrypt_password
from hh_client import HHClient, HHAuthError, HHNetworkError, HHParseError

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "🔍 Парсинг вакансий по фильтру")
async def parse_vacancies(message: types.Message):
    user_id = message.from_user.id

    if user_id == settings.ADMIN_ID:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Account).limit(1))
            account = result.scalar_one_or_none()
        if not account:
            await message.answer("❌ Нет ни одного аккаунта для парсинга.")
            return
    else:
        async with AsyncSessionLocal() as session:
            account = await session.get(Account, user_id)
            if not account:
                await message.answer("Аккаунт не найден.")
                return

    from app.worker.tasks import parse_new_vacancies_for_account
    parse_new_vacancies_for_account.delay(account.id)
    await message.answer(
        f"⏳ Запущен парсинг вакансий для аккаунта {account.username}. Это может занять некоторое время.",
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
        existing = await session.execute(
            select(Vacancy).where(Vacancy.hh_id == hh_id)
        )
        vacancy = existing.scalar_one_or_none()

    if not vacancy:
        # Если нет в БД, парсим с hh.ru
        cookies = account.cookies or {}
        if not cookies:
            # Пытаемся залогиниться
            try:
                password = decrypt_password(account.password_encrypted)
                async with HHClient({}, account.proxy) as temp_client:
                    cookies = await temp_client.login(account.username, password)
                # Сохраняем cookies
                async with AsyncSessionLocal() as session:
                    acc = await session.get(Account, account.id)
                    acc.cookies = cookies
                    await session.commit()
            except Exception as e:
                logger.error("Login failed for account %d: %s", account.id, e, exc_info=True)
                await message.answer("❌ Не удалось авторизоваться на hh.ru. Проверьте логин/пароль.")
                return

        try:
            async with HHClient(cookies, account.proxy) as client:
                details = await client.get_vacancy_details(int(hh_id))
                # Извлечение названия (можно из details.full_html)
                title_match = re.search(r'<h1[^>]*data-qa="vacancy-title"[^>]*>(.*?)</h1>', details.full_html or "", re.DOTALL)
                title = title_match.group(1).strip() if title_match else "Без названия"
        except HHAuthError:
            await message.answer("❌ Ошибка авторизации. Попробуйте обновить cookies.")
            return
        except HHNetworkError as e:
            await message.answer(f"❌ Сетевая ошибка: {e}")
            return
        except HHParseError as e:
            await message.answer(f"❌ Ошибка парсинга данных: {e}")
            return
        except Exception as e:
            logger.error("Unexpected error parsing vacancy %s: %s", hh_id, e, exc_info=True)
            await message.answer(f"❌ Неизвестная ошибка: {e}")
            return

        # Сохраняем вакансию
        async with AsyncSessionLocal() as session:
            vacancy = Vacancy(
                hh_id=hh_id,
                title=title,
                url=vacancy_url,
                description=details.description,
                check_word=extract_secret_word(details.description)
            )
            session.add(vacancy)
            await session.commit()
            await session.refresh(vacancy)

    # Генерируем письмо
    try:
        letter = await generate_cover_letter(account, vacancy, vacancy.check_word)
    except Exception as e:
        logger.error("Error generating letter: %s", e, exc_info=True)
        await message.answer(f"❌ Ошибка генерации письма: {e}")
        return

    await message.answer(
        f"📄 **Вакансия:** {vacancy.title}\n"
        f"🔗 {vacancy.url}\n\n"
        f"**Сгенерированное сопроводительное:**\n\n{letter}",
        reply_markup=get_main_keyboard(message.from_user.id),
        parse_mode="Markdown"
    )