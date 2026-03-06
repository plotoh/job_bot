FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для Playwright и gcc
RUN apt-get update && apt-get install -y \
    gcc \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Установка Poetry
RUN pip install poetry>=1.8.5

# Настройка Poetry: создавать виртуальное окружение внутри проекта
RUN poetry config virtualenvs.in-project true

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock ./

# Устанавливаем зависимости (без установки самого проекта)
RUN poetry install --no-interaction --no-ansi --no-root

# Устанавливаем браузер Playwright (chromium) и его зависимости
RUN poetry run playwright install chromium --with-deps

# Копируем код
COPY . .

CMD ["poetry", "run", "python", "-m", "app.main"]