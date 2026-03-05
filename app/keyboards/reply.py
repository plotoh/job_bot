from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from app.config import settings


def get_main_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    if user_id == settings.ADMIN_ID:
        # Для администратора только одна кнопка в ряду
        keyboard = [
            [KeyboardButton(text="👑 Админ-панель")]
        ]
    else:
        # Для обычного пользователя все кнопки
        keyboard = [
            [KeyboardButton(text="🔍 Парсинг вакансий по фильтру")],
            [KeyboardButton(text="📝 Парсинг вакансии и генерация сопроводительного")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📋 Все данные")],
            [KeyboardButton(text="🧪 Тестовый режим")],
            [KeyboardButton(text="⚙️ Настройки аккаунта")],
        ]

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
