from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from app.config import settings


def get_main_keyboard(user_id: int = None) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🔍 Парсинг вакансий по фильтру")],
        [KeyboardButton(text="📝 Парсинг вакансии и генерация сопроводительного")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📋 Все данные")],
        [KeyboardButton(text="🧪 Тестовый режим")],
        [KeyboardButton(text="⚙️ Настройки аккаунта")],
    ]
    # Если пользователь – администратор, добавляем кнопку админ-панели
    if user_id == settings.ADMIN_ID:
        keyboard.insert(0, [KeyboardButton(text="👑 Админ-панель")])  # или в конец, как удобно

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
