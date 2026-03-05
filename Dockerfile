FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей (если нужны)
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Установка poetry
RUN pip install poetry==1.8.2

# Копируем файлы зависимостей
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Копируем код
COPY . .

CMD ["python", "-m", "app.main"]