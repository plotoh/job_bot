# hh_client/utils.py
"""Утилиты для парсинга JSON из HTML-страниц hh.ru."""

import json
import re
from typing import Any, Tuple

from .exceptions import HHParseError


def extract_json_from_html(html: str, key: str) -> Any:
    """
    Извлекает JSON-объект из HTML по ключу.
    Ищет подстроку вида ,"key":{...} или ,"key":[...].
    Возвращает распарсенный объект.
    """
    # Ищем ключ: ,"key": (за которым идёт JSON)
    pattern = rf',"{key}":(.+?)(?=,\s*"|\]|\Z)'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        raise HHParseError(f"Key '{key}' not found in HTML")
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise HHParseError(f"Failed to decode JSON for key {key}: {e}")


def extract_description(html: str) -> str:
    """Извлекает текст описания вакансии из HTML (по data-qa='vacancy-description')."""
    pattern = r'<div[^>]*data-qa="vacancy-description"[^>]*>(.*?)</div>'
    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    # Удаляем HTML-теги
    text = re.sub(r'<[^>]+>', '', match.group(1))
    # Заменяем множественные пробелы/переносы
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def extract_skills(html: str) -> list[str]:
    """Извлекает ключевые навыки из HTML."""
    skills = []
    pattern = r'<span[^>]*data-qa="vacancy-key-skills"[^>]*>(.*?)</span>'
    for match in re.finditer(pattern, html, re.DOTALL):
        skill_text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        if skill_text:
            skills.append(skill_text)
    return skills
