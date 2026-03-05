# hh_client/__init__.py
"""Клиент для взаимодействия с hh.ru через HTTP (aiohttp)."""

from .client import HHClient
from .exceptions import (
    HHError,
    HHAuthError,
    HHNetworkError,
    HHRateLimitError,
    HHParseError,
)
from .models import VacancyPreview, VacancyDetails, ApplyResult

__all__ = [
    "HHClient",
    "HHError",
    "HHAuthError",
    "HHNetworkError",
    "HHRateLimitError",
    "HHParseError",
    "VacancyPreview",
    "VacancyDetails",
    "ApplyResult",
]