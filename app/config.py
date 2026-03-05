from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    BOT_TOKEN: str
    DEBUG: bool = True

    DB_HOST: str = 'localhost'
    DB_PORT: int = 5432
    DB_NAME: str = 'job_bot'
    DB_USER: str = 'postgres'
    DB_PASSWORD: str = ''

    REDIS_URL: str = 'redis://redis:6379/0'
    CELERY_BROKER_URL: str = 'redis://redis:6379/1'
    CELERY_RESULT_BACKEND: str = 'redis://redis:6379/2'

    OLLAMA_BASE_URL: str = 'http://ollama:11434'
    OLLAMA_MODEL: str = 'llama3.1:8b'

    PROXY_LIST_PATH: str = '/app/data/proxies.txt'  # файл с прокси (один на строку)
    ENCRYPTION_KEY: str = Field(..., env='ENCRYPTION_KEY')  # для шифрования паролей
    ADMIN_ID: int = Field(..., env='ADMIN_ID')  # единственный админ
    LOG_LEVEL: str = 'INFO'

    # Периоды задач (в минутах)
    PARSE_INTERVAL: int = 60
    CHECK_INVITATIONS_INTERVAL: int = 30

    DEFAULT_LETTER_TEMPLATE: ClassVar[str] = """
    {secret_word_phrase}
    {Здравствуйте|Добрый день}! {Прошу рассмотреть мою кандидатуру на|Откликаюсь на|откликаюсь на вакансию|Прошу рассмотреть мой отклик на вакансию|Меня заинтересовала вакансия} {vacancy_name}.
    {Мои опыт и навыки подходят|Под требования подхожу|Соответствую требованиям|Опыт и навыки удовлетворяют ваш запрос|Мой опыт и навыки соответствуют вашим требованиям}. 
    {Хорошего рабочего дня!|Надеюсь на ответ.|Буду рад обсудить детали.|Буду рад обсудить детали на собеседовании}
    {Мой телеграм|tg|Telegram}: {tg_username}
    """


settings = Settings()
