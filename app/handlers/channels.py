import logging

from aiogram import types, Router
from aiogram.filters import ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from sqlalchemy import select
from datetime import datetime

from app.database.models import AsyncSessionLocal, TelegramChannel, ChannelVacancy
from app.services.channel_parser import extract_vacancy_info  # функция для анализа текста

logger = logging.getLogger(__name__)
router = Router()


@router.channel_post()
async def handle_channel_post(message: types.Message):
    # Сохраняем сообщение в базу
    async with AsyncSessionLocal() as session:
        # Проверим, есть ли канал в нашей таблице (чтобы не сохранять всё подряд)
        stmt = select(TelegramChannel).where(TelegramChannel.id == message.chat.id)
        channel = (await session.execute(stmt)).scalar_one_or_none()
        if not channel or not channel.is_active:
            return

        # Проверяем, не сохраняли ли уже это сообщение
        stmt = select(ChannelVacancy).where(
            ChannelVacancy.channel_id == message.chat.id,
            ChannelVacancy.message_id == message.message_id
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            return

        # Анализируем текст, извлекаем информацию (название, компанию, контакты)
        parsed = await extract_vacancy_info(message.text or message.caption)

        vacancy = ChannelVacancy(
            channel_id=message.chat.id,
            message_id=message.message_id,
            text=message.text or message.caption or "",
            published_at=message.date,
            is_parsed=False
        )
        session.add(vacancy)
        await session.commit()
        logger.info(f"Saved new vacancy from channel {message.chat.title} (ID: {message.message_id})")
