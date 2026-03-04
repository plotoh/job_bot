# app/services/account_data.py
import json
from typing import Dict, Any
from app.database.models import Account


def format_account_data(account: Account) -> Dict[str, Any]:
    """Преобразует модель Account в словарь для отображения пользователю."""
    resume_preview = account.resume_text[:100] + "..." if len(account.resume_text) > 100 else account.resume_text
    search_filter_str = json.dumps(account.search_filter, ensure_ascii=False,
                                   indent=2) if account.search_filter else "не задан"
    proxy_str = account.proxy if account.proxy else "не используется"

    return {
        "id": account.id,
        "username": account.username,
        "resume_preview": resume_preview,
        "search_filter": search_filter_str,
        "proxy": proxy_str,
        "responses_today": account.responses_today,
        "daily_response_limit": account.daily_response_limit,
        "daily_limit_range": f"{account.daily_limit_min}–{account.daily_limit_max}",
        "response_interval_range": f"{account.response_interval_min}–{account.response_interval_max} сек",
        "work_hours": f"{account.work_start_hour}:00 – {account.work_end_hour}:00",
        "last_reset_date": account.last_reset_date,
        "test_parse": account.test_parse_vacancy,
        "test_generate": account.test_generate_letter,
        "test_send": account.test_send_response,
        "test_count": account.test_count,
    }


def format_account_text(account: Account) -> str:
    """Возвращает форматированный текст для отображения всех данных."""
    data = format_account_data(account)
    text = (
        f"📋 <b>Данные вашего аккаунта</b>\n\n"
        f"🆔 ID: <code>{data['id']}</code>\n"
        f"🔑 Логин hh: <code>{data['username']}</code>\n"
        f"📄 Резюме (начало): <code>{data['resume_preview']}</code>\n"
        f"🔎 Фильтр поиска: <pre>{data['search_filter']}</pre>\n"
        f"🌐 Прокси: <code>{data['proxy']}</code>\n\n"
        f"⚙️ <b>Лимиты и расписание</b>\n"
        f"   • Отправлено сегодня: {data['responses_today']} / {data['daily_response_limit']}\n"
        f"   • Диапазон дневного лимита: {data['daily_limit_range']}\n"
        f"   • Интервал откликов: {data['response_interval_range']}\n"
        f"   • Рабочие часы: {data['work_hours']}\n"
        f"   • Последний сброс: {data['last_reset_date']}\n\n"
        f"🧪 <b>Тестовый режим</b>\n"
        f"   • Парсить: {'✅' if data['test_parse'] else '❌'}\n"
        f"   • Генерировать: {'✅' if data['test_generate'] else '❌'}\n"
        f"   • Отправлять: {'✅' if data['test_send'] else '❌'}\n"
        f"   • Количество тестов: {data['test_count']}"
    )
    return text
