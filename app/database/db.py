from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import AsyncSessionLocal, engine, Base
import asyncpg
from app.config import settings

_pool = None


async def init_db_pool():
    """Инициализирует пул соединений с БД."""
    global _pool
    _pool = await asyncpg.create_pool(**settings, min_size=1, max_size=10)
    return _pool


async def get_pool():
    """Возвращает пул соединений (должен быть уже инициализирован)."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def close_db_pool():
    """Закрывает пул соединений."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
