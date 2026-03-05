# app/services/letter_generator.py
import random
import re
from typing import Optional

from app.database.models import Account, Vacancy
from app.config import settings


def rand_text(text: str) -> str:
    """Заменяет {вариант1|вариант2} на случайный вариант."""
    while True:
        match = re.search(r'{([^{}]+)}', text)
        if not match:
            break
        options = match.group(1).split('|')
        replacement = random.choice(options)
        text = text[:match.start()] + replacement + text[match.end():]
    return text


async def generate_cover_letter(
    account: Account,
    vacancy: Vacancy,
    secret_word: Optional[str] = None,
) -> str:
    """
    Генерирует сопроводительное письмо на основе шаблона аккаунта.
    """
    template = account.letter_template
    if not template:
        template = settings.DEFAULT_LETTER_TEMPLATE

    secret_word_phrase = f"Проверочное слово: {secret_word}" if secret_word else ""

    letter = template.replace("{vacancy_name}", vacancy.title)
    letter = letter.replace("{secret_word_phrase}", secret_word_phrase)
    letter = letter.replace("{tg_username}", account.telegram_username or "")

    letter = rand_text(letter)

    if not account.telegram_username:
        # Удаляем строки с упоминанием Telegram
        lines = letter.split('\n')
        filtered_lines = []
        for line in lines:
            if re.search(r'(Мой телеграм|tg|Telegram)\s*:\s*$', line):
                continue
            filtered_lines.append(line)
        letter = '\n'.join(filtered_lines)

    letter = re.sub(r'\n\s*\n', '\n\n', letter).strip()
    return letter