"""
Базовые утилиты для работы с БД.
Содержит:
- Кастомные исключения для слоя БД.
- Обёртку для автоматического управления сессией.
- Типизированные CRUD‑функции.
"""

import logging
from typing import Optional, TypeVar, Type, Callable, Awaitable, Any
from functools import wraps

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AsyncSessionLocal, Base
from app.services.exceptions import ObjectNotFound, ObjectAlreadyExists

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=Base)


# ---------- Декоратор для управления сессией ----------
def with_session(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """
    Декоратор, который создаёт асинхронную сессию и передаёт её в функцию.
    После выполнения сессия автоматически закрывается.
    Логирует начало и конец операции.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with AsyncSessionLocal() as session:
            logger.debug(f"Starting DB operation: {func.__name__}")
            try:
                result = await func(session, *args, **kwargs)
                logger.debug(f"Finished DB operation: {func.__name__}")
                return result
            except Exception as e:
                logger.exception(f"Error in DB operation {func.__name__}: {e}")
                raise

    return wrapper


# ---------- CRUD-функции ----------
async def get_object(
        session: AsyncSession,
        model: Type[ModelType],
        obj_id: int,
        raise_if_not_found: bool = False
) -> Optional[ModelType]:
    """
    Получает объект по ID.
    Если raise_if_not_found=True и объект не найден – выбрасывает ObjectNotFound.
    """
    obj = await session.get(model, obj_id)
    if obj is None and raise_if_not_found:
        raise ObjectNotFound(f"{model.__name__} with id {obj_id} not found")
    return obj


async def create_object(
        session: AsyncSession,
        model: Type[ModelType],
        **kwargs
) -> ModelType:
    """Создаёт объект модели с переданными атрибутами."""
    obj = model(**kwargs)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    logger.info(f"Created {model.__name__} with id {getattr(obj, 'id', None)}")
    return obj


async def update_object(
        session: AsyncSession,
        obj: ModelType,
        **kwargs
) -> ModelType:
    """Обновляет поля объекта и сохраняет изменения."""
    for key, value in kwargs.items():
        setattr(obj, key, value)
    await session.commit()
    await session.refresh(obj)
    logger.info(f"Updated {obj.__class__.__name__} with id {getattr(obj, 'id', None)}")
    return obj


async def delete_object(
        session: AsyncSession,
        obj: ModelType
) -> None:
    """Удаляет объект."""
    await session.delete(obj)
    await session.commit()
    logger.info(f"Deleted {obj.__class__.__name__} with id {getattr(obj, 'id', None)}")


async def list_objects(
        session: AsyncSession,
        model: Type[ModelType],
        **filters
):
    """
    Возвращает список объектов с возможностью фильтрации по полям.
    """
    from sqlalchemy import select
    stmt = select(model)
    for attr, value in filters.items():
        if value is not None:
            stmt = stmt.where(getattr(model, attr) == value)
    result = await session.execute(stmt)
    return result.scalars().all()


# ---------- Вспомогательная функция для получения аккаунта (пример использования) ----------
@with_session
async def get_account(session: AsyncSession, account_id: int) -> Optional[Base]:
    """Получает аккаунт по ID."""
    # from app.database.models import Account  # локальный импорт
    return await get_object(session, Account, account_id)  # Account будет импортирован там, где используется
