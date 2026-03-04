from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Парсинг вакансий по фильтру")],
            [KeyboardButton(text="📝 Парсинг вакансии и генерация сопроводительного")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📋 Мои данные")],
            [KeyboardButton(text="🧪 Тестовый режим")],
            [KeyboardButton(text="⚙️ Настройки аккаунта")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )