from cryptography.fernet import Fernet
from app.config import settings

# Проверяем наличие ключа шифрования
if not settings.ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY must be set in environment")

# Инициализируем шифр
try:
    cipher = Fernet(
        settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)
except Exception as e:
    raise ValueError(f"Invalid ENCRYPTION_KEY: {e}")


def encrypt_password(password: str) -> str:
    """Шифрует пароль и возвращает строку в base64."""
    return cipher.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """Дешифрует пароль."""
    return cipher.decrypt(encrypted.encode()).decode()
