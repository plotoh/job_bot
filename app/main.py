import asyncio
import logging

from aiogram import Bot, Dispatcher

from app import config
from app.database import init_db_pool, close_db_pool, init_tables
from app.handlers import common, vacancy, stats
from app.logger import setup_logging

# Настраиваем логирование (уровень можно взять из конфига)
logger = setup_logging(level=logging.INFO)


async def main():
    logger.info("Starting bot...")

    # Инициализация пула БД
    pool = await init_db_pool()
    await init_tables(pool)
    logger.info("Database initialized")

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(common.router)
    dp.include_router(vacancy.router)
    dp.include_router(stats.router)

    try:
        logger.info("Bot polling started")
        await dp.start_polling(bot)
    except Exception as e:
        logger.exception("Fatal error during polling")
    finally:
        await close_db_pool()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
