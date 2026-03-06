"""Кастомные исключения для сервисного слоя."""


class ServiceError(Exception):
    """Базовое исключение для всех ошибок сервисов."""
    pass


class ObjectNotFound(ServiceError):
    """Объект не найден в БД."""
    pass


class ObjectAlreadyExists(ServiceError):
    """Объект с таким ID уже существует."""
    pass


class VacancyNotFound(ServiceError):
    """Вакансия не найдена на hh.ru."""
    pass


class ResponseLimitExceeded(ServiceError):
    """Превышен лимит откликов на сегодня."""
    pass
