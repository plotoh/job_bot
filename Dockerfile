FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Установка Poetry
RUN pip install poetry>=1.8.5

# Настройка Poetry: создавать виртуальное окружение внутри проекта
RUN poetry config virtualenvs.in-project true

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock ./

# Устанавливаем зависимости (без установки самого проекта)
RUN poetry install --no-interaction --no-ansi --no-root

# Копируем код
COPY . .

CMD ["poetry", "run", "python", "-m", "app.main"]