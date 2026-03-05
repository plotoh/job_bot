import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Создаём папку для логов, если её нет
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "error.log"

# Максимальный размер файла: 10 МБ, храним 5 старых копий
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5


def setup_logging(level=logging.INFO):
    """Настраивает логирование: вывод в консоль и в файлы."""
    # Формат логов
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Обработчик для всех логов (ротация)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Обработчик только для ошибок
    error_file_handler = RotatingFileHandler(
        ERROR_LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)
    root_logger.addHandler(error_file_handler)

    # Консольный вывод (для удобства разработки)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return root_logger
