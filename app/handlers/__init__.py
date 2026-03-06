from aiogram import Router

from . import common, account_settings, test_mode, vacancy, stats
from .admin import router as admin_router
from app.handlers.common_edit import router as common_edit_router  # новый

router = Router()
router.include_router(common.router)
router.include_router(account_settings.router)
router.include_router(admin_router)
router.include_router(test_mode.router)
router.include_router(vacancy.router)
router.include_router(stats.router)
router.include_router(common_edit_router)  # добавляем