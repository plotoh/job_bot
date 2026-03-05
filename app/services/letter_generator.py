import asyncio
import logging
from typing import Optional
import ollama
from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """
Ты — опытный карьерный консультант. Твоя задача — написать персонализированное сопроводительное письмо от имени соискателя на конкретную вакансию.

Правила:
- Приветствие должно быть простым - Здравствуйте / Добрый день.
- Письмо должно быть деловым, но тёплым и конкретным. Не используй общие фразы.
- Используй информацию из резюме кандидата, чтобы показать соответствие требованиям вакансии.
- Если в описании вакансии есть проверочное слово, обязательно включи его в письмо естественным образом.
- Не упоминай зарплату.
- Длина письма — не более 500 символов.
- Структура: приветствие, выражение интереса к компании/проекту (без излишних подробностей), краткое обоснование соответствия (2-3 предложения), готовность к собеседованию, прощание.
- Не используй шаблонные фразы типа "Я узнал о вакансии...". Лучше сразу перейти к делу.
- В конце добавь что-то наподобие: На любые вопросы готов ответить в тг и tg_username

Вот информация:
- Вакансия: {vacancy_title}, компания: {company}
- Описание вакансии: {vacancy_description}
- Резюме кандидата: {resume_text}
- Проверочное слово: {secret_word}
- telegram username: {tg_username}
"""

FALLBACK_TEMPLATE = """
Здравствуйте! Меня заинтересовала вакансия {vacancy_title}. Мой опыт и навыки соответствуют вашим требованиям. 
{tg_part}
Буду рад обсудить детали.
"""


async def generate_cover_letter(
        vacancy_title: str,
        vacancy_description: str,
        company: str,
        resume_text: str,
        secret_word: Optional[str] = None,
        system_prompt: Optional[str] = None,
        tg_username: Optional[str] = None
) -> str:
    try:
        if not system_prompt:
            system_prompt = DEFAULT_SYSTEM_PROMPT

        system_prompt = system_prompt.format(
            vacancy_title=vacancy_title,
            company=company,
            vacancy_description=vacancy_description,
            resume_text=resume_text,
            secret_word=secret_word or "нет",
            tg_username=tg_username or "не указан"
        )

        client = ollama.Client(host=settings.OLLAMA_BASE_URL)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "system", "content": system_prompt}],
                options={"temperature": 0.6, "num_predict": 500}
            )
        )
        letter = response["message"]["content"].strip()
        if not letter:
            raise ValueError("LLM вернул пустой ответ")
        return letter
    except Exception as e:
        logger.error(f"Ошибка генерации письма: {e}", exc_info=True)
        tg_part = f"Мой Telegram: {tg_username}" if tg_username else ""
        return FALLBACK_TEMPLATE.format(
            vacancy_title=vacancy_title,
            company=company,
            tg_part=tg_part
        ).strip()
