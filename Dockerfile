FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для Playwright и общих нужд
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libcups2 \
    libxss1 \
    libxrandr2 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    libpango-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем браузеры для Playwright (включая системные зависимости)
RUN playwright install chromium --with-deps

COPY . .

# Команда по умолчанию (может быть переопределена в docker-compose)
CMD ["python", "-m", "app.main"]