import re
from typing import Optional

def extract_secret_word(description: str) -> Optional[str]:
    """
    Пытается найти в описании проверочное слово.
    Возвращает найденное слово или None.
    """
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

async def is_backend_python_llm(title: str, description: str, ollama_model: str = "llama3.1:8b") -> bool:
    """
    Использует LLM для определения, подходит ли вакансия (backend python).
    Возвращает True/False.
    """
    import ollama
    prompt = f"Вакансия: {title}\n\nОписание: {description[:1500]}\n\nЯвляется ли эта вакансия позицией backend-разработчика на Python? Ответь только 'да' или 'нет'."
    response = ollama.chat(
        model=ollama_model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0}
    )
    answer = response["message"]["content"].strip().lower()
    return "да" in answer

def is_backend_python_keywords(title: str, description: str) -> bool:
    """
    Быстрая фильтрация по ключевым словам.
    """
    text = (title + " " + description).lower()
    # Должен содержать python и один из backend-маркеров
    has_python = 'python' in text
    has_backend = any(kw in text for kw in ['backend', 'бэкенд', 'back-end', 'django', 'fastapi', 'flask'])
    # Не должен содержать явные признаки не backend
    not_fullstack = 'fullstack' not in text and 'full stack' not in text
    not_frontend = 'frontend' not in text and 'фронтенд' not in text
    return has_python and has_backend and not_fullstack and not_frontend