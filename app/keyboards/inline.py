from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List

from app.database.models import Account


def get_admin_main_keyboard(accounts: List[Account]) -> InlineKeyboardMarkup:
    """Клавиатура главного меню админа."""
    action_buttons = [
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="admin_add_account")],
        [InlineKeyboardButton(text="📊 Общая статистика", callback_data="admin_global_stats")],
        [InlineKeyboardButton(text="🔄 Обновить список", callback_data="admin_refresh_list")],
    ]
    account_buttons = []
    for acc in accounts:
        account_buttons.append([InlineKeyboardButton(
            text=f"{acc.username} (ID: {acc.id})",
            callback_data=f"admin_acc_{acc.id}"
        )])
    if not account_buttons:
        account_buttons.append([InlineKeyboardButton(text="📭 Нет аккаунтов", callback_data="admin_noop")])
    close_button = [[InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]]
    return InlineKeyboardMarkup(inline_keyboard=action_buttons + account_buttons + close_button)


def get_account_edit_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для редактирования конкретного аккаунта."""
    buttons = [
        [InlineKeyboardButton(text="🧪 Тестовый режим", callback_data="admin_test_mode")],
        [InlineKeyboardButton(text="✏️ Изменить фильтр", callback_data="admin_edit_filter")],
        [InlineKeyboardButton(text="📝 Изменить резюме", callback_data="admin_edit_resume")],
        [InlineKeyboardButton(text="🌐 Изменить прокси", callback_data="admin_edit_proxy")],
        [InlineKeyboardButton(text="📤 Загрузить cookies из файла", callback_data="admin_upload_cookies")],
        [InlineKeyboardButton(text="📥 Скачать cookies как файл", callback_data="admin_download_cookies")],
        [InlineKeyboardButton(text="🔢 Количество страниц парсинга", callback_data="admin_edit_max_pages")],
        [InlineKeyboardButton(text="⚙️ Лимит (диапазон)", callback_data="admin_edit_limit_range")],
        [InlineKeyboardButton(text="⏱ Интервал отклика", callback_data="admin_edit_interval")],
        [InlineKeyboardButton(text="🕒 Рабочие часы", callback_data="admin_edit_work_hours")],
        [InlineKeyboardButton(text="📱 Telegram username", callback_data="admin_edit_telegram_username")],
        [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="admin_back_to_main")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
