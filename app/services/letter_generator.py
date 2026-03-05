import random
import re
from typing import Optional

DEFAULT_TEMPLATE = """
{secret_word_phrase}
{Здравствуйте|Добрый день}! {Прошу рассмотреть мою кандидатуру на|Откликаюсь на|откликаюсь на вакансию|Прошу рассмотреть мой отклик на вакансию|Меня заинтересовала вакансия} {vacancy_name}.
{Мои опыт и навыки подходят|Под требования подхожу|Соответствую требованиям|Опыт и навыки удовлетворяют ваш запрос|Мой опыт и навыки соответствуют вашим требованиям}. 
{Хорошего рабочего дня!|Надеюсь на ответ.|Буду рад обсудить детали.|Буду рад обсудить детали на собеседовании}
{Мой телеграм|tg|Telegram}: {tg_username}
"""


def rand_text(text: str) -> str:
    """
    Заменяет конструкции {вариант1|вариант2} на случайный вариант.
    Может быть вложенным.
    """
    while True:
        match = re.search(r'{([^{}]+)}', text)
        if not match:
            break
        options = match.group(1).split('|')
        replacement = random.choice(options)
        text = text[:match.start()] + replacement + text[match.end():]
    return text


async def generate_cover_letter(
        vacancy_title: str,
        vacancy_description: str,
        company: str,  # не используется
        resume_text: str,
        secret_word: Optional[str] = None,
        system_prompt: Optional[str] = None,  # не используется
        tg_username: Optional[str] = None,
        template: Optional[str] = None
) -> str:
    """
    Генерирует сопроводительное письмо по шаблону.
    Если template не задан, используется DEFAULT_TEMPLATE.
    Поддерживаются переменные:
        {vacancy_name}, {secret_word_phrase}, {tg_username}
    """
    if not template:
        template = DEFAULT_TEMPLATE

    # Подготовка фразы про проверочное слово
    if secret_word:
        secret_word_phrase = f"Проверочное слово: {secret_word}"
    else:
        secret_word_phrase = ""

    # Подстановка переменных
    letter = template.replace("{vacancy_name}", vacancy_title)
    letter = letter.replace("{secret_word_phrase}", secret_word_phrase)
    letter = letter.replace("{tg_username}", tg_username if tg_username else "")

    # Обработка случайного выбора
    letter = rand_text(letter)

    # Если tg_username пустой, удаляем строку, содержащую упоминание Telegram
    if not tg_username:
        # Удаляем строки, где есть "Мой телеграм", "tg" или "Telegram" и двоеточие, после которого только пробелы или ничего
        lines = letter.split('\n')
        filtered_lines = []
        for line in lines:
            if re.search(r'(Мой телеграм|tg|Telegram)\s*:\s*$', line):
                continue
            filtered_lines.append(line)
        letter = '\n'.join(filtered_lines)

    # Очистка от лишних пробелов и переносов
    letter = re.sub(r'\n\s*\n', '\n\n', letter).strip()
    return letter
