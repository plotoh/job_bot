import asyncio
import re
import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


def extract_secret_word(description: str) -> Optional[str]:
    """Извлечение проверочного слова по шаблонам."""
    if not description:
        return None
    patterns = [
        r'укажите\s+слово\s+["\']?(\w+)["\']?',
        r'напишите\с+в\s+отклике\с+слово\s+["\']?(\w+)["\']?',
        r'в\с+поле\с+.*?\с+укажите\с+["\']?(\w+)["\']?',
        r'проверочное\с+слово:\с*["\']?(\w+)["\']?',
    ]
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


# import re
from typing import Optional


def extract_secret_word(description: str) -> Optional[str]:
    """Извлечение проверочного слова по шаблонам."""
    if not description:
        return None
    patterns = [
        r'укажите\s+слово\s+["\']?(\w+)["\']?',
        r'напишите\s+в\s+отклике\s+слово\s+["\']?(\w+)["\']?',
        r'в\s+поле\s+.*?\s+укажите\s+["\']?(\w+)["\']?',
        r'проверочное\s+слово:\s*["\']?(\w+)["\']?',
    ]
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def is_backend_python_keywords(title: str, description: str) -> bool:
    """Быстрая фильтрация по ключевым словам."""
    text = (title + " " + description).lower()
    has_python = 'python' in text
    has_backend = any(kw in text for kw in ['backend', 'бэкенд', 'back-end', 'django', 'fastapi', 'flask'])
    not_fullstack = 'fullstack' not in text and 'full stack' not in text
    not_frontend = 'frontend' not in text and 'фронтенд' not in text
    return has_python and has_backend and not_fullstack and not_frontend
