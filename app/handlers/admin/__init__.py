from aiogram import Router
from . import main, accounts, edit_account, add_account, test_mode, stats, prompt

router = Router()
router.include_router(main.router)
router.include_router(accounts.router)
router.include_router(edit_account.router)
router.include_router(add_account.router)
router.include_router(test_mode.router)
router.include_router(stats.router)
router.include_router(prompt.router)
