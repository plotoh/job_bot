import asyncio
import re
import logging
from typing import Optional
import ollama
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


async def extract_secret_word_llm(description: str) -> Optional[str]:
    """Использование LLM для поиска проверочного слова, если шаблоны не сработали."""
    prompt = f"Найди в тексте вакансии проверочное слово, которое кандидат должен указать в отклике. Если такого слова нет, ответь 'НЕТ'. Текст:\n\n{description[:2000]}"
    try:
        client = ollama.Client(host=settings.OLLAMA_BASE_URL)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0}
            )
        )
        answer = response["message"]["content"].strip()
        if answer.upper() == "НЕТ" or len(answer) > 50:
            return None
        return answer
    except Exception as e:
        logger.error(f"LLM secret word extraction failed: {e}")
        return None


def is_backend_python_keywords(title: str, description: str) -> bool:
    """Быстрая фильтрация по ключевым словам."""
    text = (title + " " + description).lower()
    has_python = 'python' in text
    has_backend = any(kw in text for kw in ['backend', 'бэкенд', 'back-end', 'django', 'fast api' 'fastapi', 'flask'])
    not_fullstack = 'fullstack' not in text and 'full stack' not in text
    not_frontend = 'frontend' not in text and 'фронтенд' not in text
    return has_python and has_backend and not_fullstack and not_frontend


async def is_backend_python_llm(title: str, description: str) -> bool:
    """LLM-проверка релевантности вакансии (используется, если ключевые слова дают неоднозначный результат)."""
    prompt = f"Вакансия: {title}\n\nОписание: {description[:1500]}\n\nЯвляется ли эта вакансия позицией backend-разработчика на Python? Ответь только 'да' или 'нет'."
    try:
        client = ollama.Client(host=settings.OLLAMA_BASE_URL)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0}
            )
        )
        answer = response["message"]["content"].strip().lower()
        return "да" in answer
    except Exception as e:
        logger.error(f"LLM relevance check failed: {e}")
        return False
