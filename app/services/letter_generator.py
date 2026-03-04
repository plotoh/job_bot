import asyncio
from typing import Optional
import ollama
from app.config import settings

DEFAULT_SYSTEM_PROMPT = """Ты — опытный карьерный консультант. Твоя задача — написать сопроводительное письмо от имени соискателя.

Правила:
- Письмо должно быть деловым, но тёплым и конкретным.
- Длина — не более 400 символов.
- Структура: приветствие, интерес к компании и вакансии, соответствие ключевым требованиям (с примерами из опыта), благодарность и готовность к собеседованию.
- Не используй шаблонные фразы, избегай общих слов.
- Не упоминай зарплату."""


async def generate_cover_letter(
        vacancy_title: str,
        vacancy_description: str,
        company: str,
        resume_text: str,
        secret_word: Optional[str] = None,
        system_prompt: Optional[str] = None
) -> str:
    """
    Генерирует сопроводительное письмо с помощью локальной Ollama.
    """
    truncated_desc = vacancy_description[:1500] + ("..." if len(vacancy_description) > 1500 else "")

    # Используем переданный промпт или стандартный
    prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT

    if secret_word:
        prompt += f"\n- ВАЖНО: обязательно включи в письмо проверочное слово '{secret_word}' естественным образом."

    user_prompt = f"""
Информация о вакансии:
- Должность: {vacancy_title}
- Компания: {company}
- Описание: {truncated_desc}

Информация о кандидате (резюме):
{resume_text}

Напиши сопроводительное письмо от имени кандидата.
"""

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_prompt}
            ],
            options={"temperature": 0.7, "num_predict": 800}
        )
    )
    return response["message"]["content"].strip()
