from aiogram import Router

from . import common, account_settings, admin_panel, test_mode, vacancy, stats

router = Router()
router.include_router(common.router)
router.include_router(account_settings.router)
router.include_router(admin_panel.router)
router.include_router(test_mode.router)
router.include_router(vacancy.router)
router.include_router(stats.router)
