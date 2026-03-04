from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import AsyncSessionLocal, engine, Base


async def init_db():
    """Создает таблицы в базе данных (если их нет)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Генератор асинхронных сессий (для зависимостей FastAPI, если потребуется)."""
    async with AsyncSessionLocal() as session:
        yield session
