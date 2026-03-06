import logging
from typing import Optional, Callable, Awaitable, Any, Union

from aiogram import types, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.fsm.states import CommonEditStates
from app.services import account_crud as crud
from app.services.exceptions import ObjectNotFound, ServiceError

logger = logging.getLogger(__name__)
router = Router()

# Типы для обработчиков
FieldValidator = Callable[[str], Optional[Any]]   # принимает сырой ввод, возвращает валидное значение или None
FieldUpdater = Callable[[int, Any], Awaitable[Any]]  # принимает account_id и значение, возвращает обновлённый аккаунт


class FieldEditHandler:
    """Обработчик для конкретного поля."""
    def __init__(self, prompt: str, validator: FieldValidator, updater: FieldUpdater, success_message: str):
        self.prompt = prompt
        self.validator = validator
        self.updater = updater
        self.success_message = success_message


# Словарь всех доступных полей для редактирования
FIELD_HANDLERS: dict[str, FieldEditHandler] = {}


def register_field(name: str, handler: FieldEditHandler) -> None:
    """Регистрирует поле для редактирования."""
    FIELD_HANDLERS[name] = handler


# ---------- Валидаторы для разных типов полей ----------

def validate_not_empty(value: str) -> Optional[str]:
    """Просто проверяет, что строка не пустая."""
    return value if value.strip() else None


def validate_url(value: str) -> Optional[str]:
    """Проверяет, что строка начинается с http:// или https://."""
    return value if value.startswith(('http://', 'https://')) else None


def validate_optional_string(value: str) -> Optional[str]:
    """Принимает любую строку, '-' преобразует в None."""
    return None if value == '-' else value


def validate_limit_range(value: str) -> Optional[tuple[int, int]]:
    """Парсит строку вида 'min max' и возвращает кортеж."""
    parts = value.split()
    if len(parts) != 2:
        return None
    try:
        min_lim, max_lim = map(int, parts)
        if min_lim <= 0 or min_lim > max_lim:
            return None
        return (min_lim, max_lim)
    except ValueError:
        return None


def validate_interval_range(value: str) -> Optional[tuple[int, int]]:
    """Аналогично для интервала (секунды)."""
    parts = value.split()
    if len(parts) != 2:
        return None
    try:
        min_int, max_int = map(int, parts)
        if min_int <= 0 or min_int > max_int:
            return None
        return (min_int, max_int)
    except ValueError:
        return None


def validate_work_hours(value: str) -> Optional[tuple[int, int]]:
    """Парсит часы работы 'start end'."""
    parts = value.split()
    if len(parts) != 2:
        return None
    try:
        start, end = map(int, parts)
        if not (0 <= start < 24) or not (0 <= end <= 24) or start >= end:
            return None
        return (start, end)
    except ValueError:
        return None


def validate_positive_int(value: str) -> Optional[int]:
    """Проверяет, что строка является положительным целым числом."""
    try:
        num = int(value)
        if num <= 0:
            return None
        return num
    except ValueError:
        return None


# ---------- Регистрация всех полей ----------

register_field('telegram_username', FieldEditHandler(
    prompt="Введите новый Telegram username (например, @username) или '-' чтобы удалить:",
    validator=validate_optional_string,
    updater=crud.update_account_telegram_username,
    success_message="✅ Telegram username обновлён!"
))

register_field('filter', FieldEditHandler(
    prompt="Введите новый URL фильтра (например, https://hh.ru/search/vacancy?text=Python):",
    validator=validate_url,
    updater=crud.update_account_filter,
    success_message="✅ Фильтр обновлён!"
))

register_field('resume', FieldEditHandler(
    prompt="Отправьте новый текст резюме:",
    validator=validate_not_empty,
    updater=crud.update_account_resume,
    success_message="✅ Резюме обновлено!"
))

register_field('proxy', FieldEditHandler(
    prompt="Введите новый прокси (например, http://user:pass@host:port) или '-' для удаления:",
    validator=validate_optional_string,
    updater=crud.update_account_proxy,
    success_message="✅ Прокси обновлён!"
))

register_field('limit_range', FieldEditHandler(
    prompt="Введите минимальный и максимальный лимит через пробел (например: 50 100):",
    validator=validate_limit_range,
    updater=lambda acc_id, val: crud.update_account_limit_range(acc_id, val[0], val[1]),
    success_message="✅ Диапазон лимита обновлён!"
))

register_field('interval_range', FieldEditHandler(
    prompt="Введите минимальный и максимальный интервал между откликами в секундах через пробел (например: 120 480):",
    validator=validate_interval_range,
    updater=lambda acc_id, val: crud.update_account_interval_range(acc_id, val[0], val[1]),
    success_message="✅ Интервал откликов обновлён!"
))

register_field('work_hours', FieldEditHandler(
    prompt="Введите часы начала и окончания работы через пробел (например: 10 17):",
    validator=validate_work_hours,
    updater=lambda acc_id, val: crud.update_account_work_hours(acc_id, val[0], val[1]),
    success_message="✅ Рабочие часы обновлены!"
))

register_field('max_pages', FieldEditHandler(
    prompt="Введите новое максимальное количество страниц для парсинга (целое число, например 3):",
    validator=validate_positive_int,
    updater=crud.update_account_max_pages,
    success_message="✅ Количество страниц обновлено!"
))


# ---------- Основная функция для старта редактирования ----------

async def start_editing(
    update: Union[Message, CallbackQuery],
    state: FSMContext,
    field: str,
    mode: str,                 # 'admin' или 'user'
    account_id: Optional[int] = None,   # для admin можно передать явно
) -> None:
    """
    Универсальная функция для начала редактирования поля.
    Подходит как для сообщений (из пользовательских настроек), так и для колбэков (из админки).
    """
    if field not in FIELD_HANDLERS:
        text = "❌ Неизвестное поле для редактирования."
        if isinstance(update, CallbackQuery):
            await update.answer(text, show_alert=True)
        else:
            await update.answer(text)
        return

    # Определяем account_id
    if mode == 'user':
        acc_id = update.from_user.id
    else:  # admin
        if account_id is not None:
            acc_id = account_id
        else:
            data = await state.get_data()
            acc_id = data.get('account_id')
            if not acc_id:
                if isinstance(update, CallbackQuery):
                    await update.answer("❌ Не выбран аккаунт. Начните заново.", show_alert=True)
                else:
                    await update.answer("❌ Не выбран аккаунт. Начните заново.")
                return

    # Сохраняем данные в состоянии
    await state.update_data(field=field, mode=mode, account_id=acc_id)

    handler = FIELD_HANDLERS[field]
    prompt = handler.prompt

    if isinstance(update, CallbackQuery):
        await update.message.edit_text(prompt)
        await update.answer()
    else:
        await update.answer(prompt)

    await state.set_state(CommonEditStates.waiting_value)


# ---------- Обработчик введённого значения ----------

@router.message(StateFilter(CommonEditStates.waiting_value))
async def process_edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data.get('field')
    mode = data.get('mode')
    account_id = data.get('account_id')

    if not field or not mode or not account_id:
        await message.answer("❌ Сессия истекла. Начните заново.")
        await state.clear()
        return

    handler = FIELD_HANDLERS.get(field)
    if not handler:
        await message.answer("❌ Ошибка конфигурации. Попробуйте позже.")
        await state.clear()
        return

    raw_value = message.text.strip()
    validated = handler.validator(raw_value)

    if validated is None:
        await message.answer("❌ Некорректное значение. Попробуйте ещё раз или отмените командой /cancel")
        return

    try:
        # Вызываем соответствующую функцию обновления
        if isinstance(validated, tuple):
            # Для полей, возвращающих кортеж (диапазоны)
            await handler.updater(account_id, *validated)
        else:
            await handler.updater(account_id, validated)

        await message.answer(handler.success_message)
        logger.info(f"Field '{field}' updated for account {account_id}", extra={"account_id": account_id, "field": field})

    except ObjectNotFound:
        await message.answer("❌ Аккаунт не найден. Возможно, он был удалён.")
        await state.clear()
        return
    except ServiceError as e:
        await message.answer(f"❌ Ошибка сервиса: {e}")
        logger.exception(f"Service error while updating {field} for account {account_id}")
        await state.clear()
        return
    except Exception as e:
        await message.answer(f"❌ Неизвестная ошибка: {e}")
        logger.exception(f"Unexpected error while updating {field} for account {account_id}")
        await state.clear()
        return

    # Возвращаем пользователя в соответствующее меню
    if mode == 'admin':
        from app.handlers.admin.common import show_account_menu
        await show_account_menu(message, account_id, state)
    else:
        from app.handlers.account_settings import show_settings_menu
        await show_settings_menu(message, state)