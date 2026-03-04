from aiogram import types, F, Router
from sqlalchemy import select, func, and_
from datetime import date

from app.database.models import AsyncSessionLocal, Account, Response, Invitation
from app.keyboards.reply import get_main_keyboard

router = Router()


@router.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    telegram_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        # Получаем аккаунт пользователя
        account = await session.get(Account, telegram_id)
        if not account:
            await message.answer("У вас нет привязанного аккаунта.", reply_markup=get_main_keyboard())
            return

        # Сегодняшние отклики
        today = date.today()
        stmt_today = select(func.count()).where(
            and_(
                Response.account_id == account.id,
                func.date(Response.created_at) == today
            )
        )
        today_responses = await session.scalar(stmt_today) or 0

        # Всего откликов
        total_responses = await session.scalar(
            select(func.count()).where(Response.account_id == account.id)
        ) or 0

        # Приглашения
        total_invitations = await session.scalar(
            select(func.count()).where(Invitation.account_id == account.id)
        ) or 0

        # Дополнительно: лимит на сегодня
        limit_today = account.daily_response_limit
        remaining = max(0, limit_today - account.responses_today)

    text = (
        f"📊 **Статистика для аккаунта {account.username}**\n\n"
        f"📅 Откликов сегодня: {today_responses} (осталось: {remaining})\n"
        f"📦 Всего откликов: {total_responses}\n"
        f"📬 Приглашений на собеседование: {total_invitations}"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

from aiogram import types, F, Router
from sqlalchemy import select, func, and_
from datetime import date
import json

from app.database.models import AsyncSessionLocal, Account, Response, Invitation
from app.keyboards.reply import get_main_keyboard

router = Router()

# ... существующий обработчик show_stats ...

@router.message(F.text == "📋 Мои данные")
async def show_my_data(message: types.Message):
    telegram_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        account = await session.get(Account, telegram_id)
        if not account:
            await message.answer("У вас нет привязанного аккаунта.", reply_markup=get_main_keyboard())
            return

        # Статистика
        today = date.today()
        today_resp = await session.scalar(
            select(func.count()).where(
                Response.account_id == account.id,
                func.date(Response.created_at) == today
            )
        ) or 0
        total_resp = await session.scalar(
            select(func.count()).where(Response.account_id == account.id)
        ) or 0
        total_inv = await session.scalar(
            select(func.count()).where(Invitation.account_id == account.id)
        ) or 0

        # Формируем текст
        resume_preview = account.resume_text[:100] + "..." if len(account.resume_text) > 100 else account.resume_text
        search_filter_str = json.dumps(account.search_filter, ensure_ascii=False, indent=2) if account.search_filter else "не задан"
        proxy_str = account.proxy if account.proxy else "не используется"

        text = (
            f"📋 <b>Данные вашего аккаунта</b>\n\n"
            f"🆔 ID: <code>{account.id}</code>\n"
            f"🔑 Логин hh: <code>{account.username}</code>\n"
            f"📄 Резюме (начало): <code>{resume_preview}</code>\n"
            f"🔎 Фильтр поиска: <pre>{search_filter_str}</pre>\n"
            f"🌐 Прокси: <code>{proxy_str}</code>\n\n"
            f"⚙️ <b>Лимиты и расписание</b>\n"
            f"   • Дневной лимит: {account.responses_today}/{account.daily_response_limit}\n"
            f"   • Диапазон лимита: {account.daily_limit_min}–{account.daily_limit_max}\n"
            f"   • Интервал откликов: {account.response_interval_min}–{account.response_interval_max} сек\n"
            f"   • Рабочие часы: {account.work_start_hour}:00 – {account.work_end_hour}:00\n\n"
            f"📊 <b>Статистика</b>\n"
            f"   • Откликов сегодня: {today_resp}\n"
            f"   • Всего откликов: {total_resp}\n"
            f"   • Приглашений: {total_inv}\n"
            f"   • Последний сброс лимита: {account.last_reset_date}\n\n"
            f"🧪 <b>Тестовый режим</b>\n"
            f"   • Парсить: {'✅' if account.test_parse_vacancy else '❌'}\n"
            f"   • Генерировать: {'✅' if account.test_generate_letter else '❌'}\n"
            f"   • Отправлять: {'✅' if account.test_send_response else '❌'}\n"
            f"   • Количество тестов: {account.test_count}"
        )

    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")