from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable

from app.database.models import AsyncSessionLocal, Account
from app.config import settings


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id

        # Проверяем наличие аккаунта в БД
        async with AsyncSessionLocal() as session:
            account = await session.get(Account, user_id)

        # Если аккаунта нет и пользователь не админ — блокируем
        if not account and user_id != settings.ADMIN_ID:
            if isinstance(event, Message):
                await event.answer("🚫 У тебя нет доступа. Но его и не должно быть) \nПока")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Нет доступа", show_alert=True)
            return  # Прерываем обработку

        # Передаём user_id в data для использования в хэндлерах (например, для клавиатуры)
        data['user_id'] = user_id
        return await handler(event, data)