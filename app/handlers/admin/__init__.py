from aiogram import Router

from . import main, edit_account, cookies, add_account

router = Router()
router.include_router(main.router)
router.include_router(edit_account.router)
router.include_router(cookies.router)
router.include_router(add_account.router)

__all__ = ["router"]