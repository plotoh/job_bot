# 🤖 HeadHunter Bot (job-bot)

> Telegram-бот для автоматизации поиска и откликов на вакансии на [hh.ru](https://hh.ru)

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-blue.svg)](https://docs.aiogram.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Telegram-бот для автоматизации поиска и откликов на вакансии на hh.ru. Бот позволяет управлять несколькими аккаунтами,
настраивать фильтры поиска, шаблоны сопроводительных писем, а также отправлять отклики по расписанию.

---

## 📋 Оглавление

- [🚀 Возможности](#-возможности)
- [🛠 Технологии](#-технологии)
- [📦 Установка и запуск](#-установка-и-запуск)
    - [Локальная разработка](#локальная-разработка)
    - [Запуск в Docker](#запуск-в-docker)
- [🗂 Структура проекта](#-структура-проекта)
- [📖 Использование](#-использование)
- [⚙️ Настройка фильтра](#️-настройка-фильтра)
- [📝 Шаблоны писем](#-шаблоны-писем)
- [🔄 Миграции базы данных](#-миграции-базы-данных)
- [🧪 Тестирование](#-тестирование)
- [🤝 Вклад в разработку](#-вклад-в-разработку)
- [📄 Лицензия](#-лицензия)

---

## 🚀 Возможности

| Функция                            | Описание                                                                                     |
|------------------------------------|----------------------------------------------------------------------------------------------|
| **👥 Многопользовательский режим** | Поддержка нескольких аккаунтов с индивидуальными настройками                                 |
| **🔍 Парсинг вакансий**            | Поиск новых вакансий по заданному URL фильтра с учётом количества страниц                    |
| **🎯 Фильтрация**                  | Отбор вакансий по ключевым словам, исключениям и другим критериям (настраивается через JSON) |
| **✉️ Генерация писем**             | Шаблонизация сопроводительных писем со случайным выбором вариантов и подстановкой переменных |
| **⏰ Автоотклики**                  | Отправка откликов по расписанию с соблюдением дневных лимитов и интервалов                   |
| **🧠 Поддержка тестов**            | Автоматическое решение тестовых заданий (средний вариант ответа или "Да")                    |
| **🧪 Тестовый режим**              | Проверка генерации писем без реальной отправки                                               |
| **🍪 Управление cookies**          | Загрузка/выгрузка cookies в формате Netscape для авторизации на hh.ru                        |
| **👑 Админ-панель**                | Управление аккаунтами, просмотр статистики, редактирование параметров                        |

---

## 🛠 Технологии

```yaml
Core:
  - Python 3.11+
  - Aiogram 3.x          # Telegram Bot API
  - Pydantic             # Валидация настроек и данных

Async & Tasks:
  - Celery + Redis       # Асинхронные задачи и планировщик
  - aiohttp              # Асинхронные HTTP-запросы к hh.ru

Database:
  - PostgreSQL
  - SQLAlchemy 2.0 + asyncpg
  - Alembic              # Миграции БД

DevOps:
  - Docker + Docker Compose
  - Poetry               # Управление зависимостями
```

---

## 📦 Установка и запуск

### 🔧 Локальная разработка

#### 1. Клонирование репозитория

```bash
git clone https://github.com/yourusername/job-bot.git
cd job-bot
```

#### 2. Установка Poetry (если не установлен)

```bash
pip install poetry
```

#### 3. Установка зависимостей

```bash
# Poetry создаст и активирует виртуальное окружение автоматически
poetry install
```

#### 4. Настройка переменных окружения

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Заполните необходимые переменные:

```env
# Telegram
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_id

# Database (PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=job_bot
DB_USER=postgres
DB_PASSWORD=postgres

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Security
ENCRYPTION_KEY=your_encryption_key_for_passwords
```

#### 5. Запуск зависимостей (PostgreSQL + Redis)

```bash
# Через Docker Compose (только инфраструктура)
docker-compose up -d postgres redis
```

#### 6. Применение миграций

```bash
poetry run alembic upgrade head
```

#### 7. Запуск сервисов

> 💡 Запускайте каждый сервис в отдельном терминале или используйте `tmux`/`screen`

```bash
# Telegram бот
poetry run python -m app.main

# Celery worker (в новом терминале)
poetry run celery -A app.worker.celery_app worker --loglevel=info

# Celery beat - планировщик задач (в новом терминале)
poetry run celery -A app.worker.celery_app beat --loglevel=info
```

---

### 🐳 Запуск в Docker

#### 1. Подготовка

Убедитесь, что файл `.env` настроен (см. [выше](#4-настройка-переменных-окружения)).

#### 2. Запуск всех сервисов

```bash
docker-compose up -d --build
```

#### 3. Контейнеры

| Сервис     | Описание                  | Порт   |
|------------|---------------------------|--------|
| `postgres` | База данных               | `5432` |
| `redis`    | Брокер сообщений / кэш    | `6379` |
| `bot`      | Telegram бот              | —      |
| `worker`   | Celery worker             | —      |
| `beat`     | Celery beat (планировщик) | —      |

#### 4. Просмотр логов

```bash
# Все логи
docker-compose logs -f

# Лог конкретного сервиса
docker-compose logs -f bot
```

#### 5. Остановка

```bash
docker-compose down
```

---

## 🗂 Структура проекта

```
job-bot/
├── app/
│   ├── database/          # 🗄 Модели БД и сессия SQLAlchemy
│   ├── fsm/               # 🔄 Состояния FSM для Aiogram
│   ├── handlers/          # ⌨️ Обработчики команд (модульная структура)
│   │   ├── admin/         # 👑 Админ-панель
│   │   └── user/          # 👤 Пользовательские команды
│   ├── keyboards/         # ⌨️ Inline и Reply клавиатуры
│   ├── middlewares/       # 🔐 Мидлвари (авторизация, логирование)
│   ├── services/          # ⚙️ Бизнес-логика
│   │   ├── accounts.py    # Управление аккаунтами
│   │   ├── vacancies.py   # Работа с вакансиями
│   │   └── responses.py   # Генерация и отправка откликов
│   ├── utils/             # 🧰 Вспомогательные утилиты
│   │   ├── crypto.py      # Шифрование чувствительных данных
│   │   └── proxy.py       # Работа с прокси
│   ├── worker/            # 🕐 Задачи Celery
│   ├── config.py          # ⚙️ Конфигурация (Pydantic Settings)
│   ├── logger.py          # 📋 Настройки логирования
│   └── main.py            # 🚀 Точка входа
├── hh_client/             # 🌐 Асинхронный клиент для hh.ru
├── alembic/               # 🗃 Миграции базы данных
├── data/                  # 📁 Внешние данные (proxy, cookies)
├── logs/                  # 📜 Логи приложения
├── .env.example           # 📝 Шаблон переменных окружения
├── .gitignore             # 🚫 Исключения для Git
├── docker-compose.yml     # 🐳 Конфигурация Docker Compose
├── Dockerfile             # 📦 Сборка образа
├── pyproject.toml         # 📦 Зависимости Poetry
├── README.md              # 📖 Этот файл
└── alembic.ini            # ⚙️ Конфигурация Alembic
```

---

## 📖 Использование

После запуска бота отправьте команду `/start`. Появится клавиатура с основными действиями:

| Кнопка                    | Описание                                                                   |
|---------------------------|----------------------------------------------------------------------------|
| 🔍 **Парсинг вакансий**   | Запускает поиск новых вакансий согласно настройкам аккаунта                |
| 📝 **Генерация письма**   | Ввод ссылки на вакансию → получение описания + генерация сопроводительного |
| 📊 **Статистика**         | Просмотр метрик: отклики сегодня, всего, приглашения                       |
| 📋 **Все данные**         | Просмотр всех настроек текущего аккаунта                                   |
| 🧪 **Тестовый режим**     | Проверка генерации писем без реальной отправки                             |
| ⚙️ **Настройки аккаунта** | Изменение логина/пароля, прокси, фильтра, резюме, Telegram username        |
| 📖 **Инструкция**         | Подробная справка (также доступна по команде `/instructions`)              |

### 👑 Админ-панель

Доступна только пользователю, указанному в `ADMIN_ID`:

- ➕ Создание новых аккаунтов
- ✏️ Редактирование любых параметров
- 🍪 Загрузка/выгрузка cookies в формате Netscape
- 📈 Общая статистика по всем аккаунтам

---

## ⚙️ Настройка фильтра

Поле `search_filter` в базе данных хранит JSON с параметрами поиска.

### Пример конфигурации:

```json
{
  "url": "https://hh.ru/search/vacancy?text=python&search_field=name",
  "keywords": [
    "backend",
    "django",
    "fastapi"
  ],
  "exclude_keywords": [
    "fullstack",
    "senior",
    "стажёр"
  ],
  "use_keyword_filter": true,
  "min_salary": 100000,
  "experience": [
    "middle",
    "senior"
  ]
}
```

### Параметры фильтра:

| Параметр             | Тип             | Описание                                         |
|----------------------|-----------------|--------------------------------------------------|
| `url`                | `string`        | Базовый URL поиска на hh.ru                      |
| `keywords`           | `array[string]` | Ключевые слова для включения                     |
| `exclude_keywords`   | `array[string]` | Ключевые слова для исключения                    |
| `use_keyword_filter` | `boolean`       | Включить/отключить фильтрацию по ключевым словам |
| `min_salary`         | `number`        | Минимальная зарплата (опционально)               |
| `experience`         | `array[string]` | Требуемый опыт работы (опционально)              |

---

## 📝 Шаблоны писем

Шаблон письма хранится в поле `letter_template` аккаунта.

### 🔁 Поддерживаемые переменные:

```jinja2
{vacancy_name}        # Название вакансии
{secret_word_phrase}  # Проверочное слово из вакансии
{tg_username}         # Ваш Telegram username
```

### 🎲 Случайный выбор вариантов:

```jinja2
{Здравствуйте|Добрый день|Приветствую}, меня заинтересовала вакансия!
```

> При генерации случайно выбирается один из вариантов, разделённых `|`.

### 📄 Дефолтный шаблон

Если шаблон не задан, используется значение из `config.py`:

```python
DEFAULT_LETTER_TEMPLATE = (
    "{Здравствуйте|Добрый день}!\n"
    "Меня заинтересовала вакансия «{vacancy_name}».\n"
    "Готов обсудить детали в личном сообщении.\n"
    "Мой Telegram: @{tg_username}"
)
```

---

## 🔄 Миграции базы данных

При изменениях в моделях (`app/database/models.py`):

```bash
# 1. Создание новой миграции
poetry run alembic revision --autogenerate -m "описание изменений"

# 2. Применение миграции
poetry run alembic upgrade head

# 3. (Опционально) Откат миграции
poetry run alembic downgrade -1
```

### Полезные команды Alembic:

```bash
# Просмотр истории миграций
poetry run alembic history

# Проверка текущей ревизии
poetry run alembic current

# Создание пустой миграции
poetry run alembic revision -m "manual changes"
```

---

## 🧪 Тестирование

> 🚧 Раздел в разработке. В ближайшее время будет добавлено:
> - Юнит-тесты с `pytest`
> - Интеграционные тесты с `pytest-asyncio`
> - Покрытие для сервисов и обработчиков

### Запуск тестов (когда будут добавлены):

```bash
# Все тесты
poetry run pytest

# С покрытием
poetry run pytest --cov=app

# Конкретный модуль
poetry run pytest tests/test_vacancy_parser.py
```

---

## 🤝 Вклад в разработку

Приветствуются пул-реквесты! 🎉

1. **Форкните** репозиторий
2. **Создайте ветку** для новой фичи:
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Зафиксируйте изменения**:
   ```bash
   git commit -m '✨ Add some amazing feature'
   ```
4. **Отправьте в форк**:
   ```bash
   git push origin feature/amazing-feature
   ```
5. **Откройте Pull Request** 🚀

### 📏 Стандарты кода

Проект использует:

- [Black](https://black.readthedocs.io/) — форматирование кода
- [Ruff](https://docs.astral.sh/ruff/) — линтинг и исправления
- [pre-commit](https://pre-commit.com/) — хуки для автоматической проверки

Установите хуки перед началом работы:

```bash
poetry run pre-commit install
```

---

## 📄 Лицензия

Распространяется под лицензией **MIT**. Подробности в файле [LICENSE](LICENSE).

```
MIT License

Copyright (c) 2024 Your Name

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

> 💡 **Совет**: Добавьте этот проект в избранное ⭐, если он оказался полезным!

*Сделано с ❤️ для автоматизации поиска работы*