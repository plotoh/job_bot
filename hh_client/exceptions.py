# hh_client/exceptions.py
"""Собственные исключения для клиента hh.ru."""


class HHError(Exception):
    """Базовое исключение для всех ошибок клиента hh.ru."""
    pass


class HHAuthError(HHError):
    """Ошибка аутентификации (невалидные cookies, проблемы с логином)."""
    pass


class HHNetworkError(HHError):
    """Ошибка сети (таймаут, недоступность и т.п.)."""
    pass


class HHRateLimitError(HHError):
    """Достигнут лимит откликов на стороне hh.ru."""
    pass


class HHParseError(HHError):
    """Ошибка парсинга ответа от hh.ru (неожиданный формат)."""
    pass
