import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import settings
from app.database.db import init_db
from app.handlers import common, vacancy, stats, account, test_mode, admin
from app.logger import setup_logging
from app.middlewares.access_check import AccessMiddleware

# Настраиваем логирование (уровень можно взять из конфига)
logger = setup_logging(level=logging.INFO)


async def main():
    logger.info("Starting bot...")

    # Инициализация пула БД
    await init_db()
    logger.info("Database initialized")

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем middleware для проверки доступа
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    dp.include_router(common.router)
    dp.include_router(vacancy.router)
    dp.include_router(stats.router)
    dp.include_router(account.router)
    dp.include_router(test_mode.router)
    dp.include_router(admin.router)  # если ещё не подключили

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
