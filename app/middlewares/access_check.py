from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable

from app.database.models import AsyncSessionLocal, Account
from app.config import settings


class AccessMiddleware(BaseMiddleware):
    """
    Middleware для проверки наличия аккаунта пользователя в БД.
    Если пользователь не найден и не является админом, отправляет сообщение об отказе.
    """
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id

        # Пропускаем команды /start и /help без проверки
        if isinstance(event, Message) and event.text and event.text.startswith(('/start', '/help')):
            return await handler(event, data)

        # Проверяем наличие аккаунта в БД
        async with AsyncSessionLocal() as session:
            account = await session.get(Account, user_id)

        # Если аккаунта нет и пользователь не админ — блокируем
        if not account and user_id != settings.ADMIN_ID:
            # Отправляем сообщение об ошибке (для callback нужно ответить)
            if isinstance(event, Message):
                await event.answer("🚫 У тебя нет доступа. Но вероятно его и не должно быть) Сорянчик")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Нет доступа", show_alert=True)
            return  # Прерываем обработку

        # Всё хорошо — передаём управление дальше
        return await handler(event, data)