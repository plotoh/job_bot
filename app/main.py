import asyncio
import logging

from aiogram import Bot, Dispatcher

from app import config
from app.config import settings
from app.database import init_db_pool, close_db_pool, init_tables
from app.database.db import init_db
from app.handlers import common, vacancy, stats
from app.logger import setup_logging
from app.handlers import account

# Настраиваем логирование (уровень можно взять из конфига)
logger = setup_logging(level=logging.INFO)


async def main():
    logger.info("Starting bot...")

    # Инициализация пула БД
    pool = await init_db()
    logger.info("Database initialized")

    bot = Bot(token=settings.get("BOT_TOKEN"))
    dp = Dispatcher()

    dp.include_router(common.router)
    dp.include_router(vacancy.router)
    dp.include_router(stats.router)
    dp.include_router(account.router)

    try:
        logger.info("Bot polling started")
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception("Fatal error during polling")
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
