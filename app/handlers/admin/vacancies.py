import logging
from aiogram import types, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from sqlalchemy import select, func

from app.database.models import AsyncSessionLocal, Vacancy
from app.config import settings

logger = logging.getLogger(__name__)
router = Router()

ITEMS_PER_PAGE = 5  # количество вакансий на странице


async def show_vacancies_page(message: types.Message, page: int = 0):
    """Отображает страницу со списком вакансий."""
    async with AsyncSessionLocal() as session:
        total = await session.scalar(select(func.count(Vacancy.id)))
        offset = page * ITEMS_PER_PAGE
        result = await session.execute(
            select(Vacancy).order_by(Vacancy.created_at.desc()).offset(offset).limit(ITEMS_PER_PAGE)
        )
        vacancies = result.scalars().all()

    text = f"📋 <b>Все вакансии (всего: {total})</b>\n\n"
    if not vacancies:
        text += "Вакансий нет."
    else:
        for vac in vacancies:
            text += f"• <a href='{vac.url}'>{vac.title}</a> (ID: {vac.hh_id})\n"

    # Кнопки пагинации
    buttons = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"vac_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page + 1}", callback_data="vac_current"))
    if (page + 1) * ITEMS_PER_PAGE < total:
        nav_row.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"vac_page_{page + 1}"))
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_back_to_main")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data.startswith("vac_page_"))
async def vacancy_page_callback(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    await show_vacancies_page(callback.message, page)
    await callback.answer()


@router.callback_query(F.data == "vac_current")
async def vac_current(callback: CallbackQuery):
    await callback.answer()

# Добавляем кнопку в главное меню админа (в файле app/handlers/admin/main.py)
# В функции admin_main_menu добавьте кнопку:
# [InlineKeyboardButton(text="📋 Все вакансии", callback_data="admin_list_vacancies")]
