from aiogram import Router
from . import data, settings, stats, test_mode, vacancy

router = Router()
router.include_router(data.router)
router.include_router(settings.router)
router.include_router(stats.router)
router.include_router(test_mode.router)
router.include_router(vacancy.router)
