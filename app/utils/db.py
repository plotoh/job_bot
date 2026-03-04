from app.database.models import AsyncSessionLocal


async def get_session():
    """Контекстный менеджер для получения сессии (опционально)."""
    async with AsyncSessionLocal() as session:
        yield session
