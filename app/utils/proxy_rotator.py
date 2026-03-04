import os
import random
from typing import Optional, Dict, List
from urllib.parse import urlparse
from app.config import settings


class ProxyRotator:
    """
    Загружает список прокси из файла и предоставляет их для аккаунтов.
    Формат файла: одна строка = один прокси.
    Поддерживаемые форматы:
      - protocol://user:pass@host:port
      - host:port (будет преобразовано в http://host:port)
    """

    def __init__(self, proxy_file: str = None):
        self.proxy_file = proxy_file or settings.PROXY_LIST_PATH
        self.proxies: List[Dict[str, str]] = []
        self._load_proxies()

    def _load_proxies(self):
        if not os.path.exists(self.proxy_file):
            # Если файла нет, просто оставляем список пустым
            return
        with open(self.proxy_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            proxy = self._parse_proxy(line)
            if proxy:
                self.proxies.append(proxy)

    def _parse_proxy(self, line: str) -> Optional[Dict[str, str]]:
        """Преобразует строку в формат Playwright."""
        if '://' in line:
            parsed = urlparse(line)
            scheme = parsed.scheme
            host = parsed.hostname
            port = parsed.port
            user = parsed.username
            password = parsed.password
            if host and port:
                proxy_dict = {'server': f'{scheme}://{host}:{port}'}
                if user and password:
                    proxy_dict['username'] = user
                    proxy_dict['password'] = password
                return proxy_dict
        else:
            parts = line.split(':')
            if len(parts) == 2:
                host, port = parts
                try:
                    int(port)
                    return {'server': f'http://{host}:{port}'}
                except ValueError:
                    pass
        return None

    def get_proxy(self, account_id: int) -> Optional[Dict[str, str]]:
        """Возвращает прокси для аккаунта (по индексу)."""
        if not self.proxies:
            return None
        index = account_id % len(self.proxies)
        return self.proxies[index]

    def get_random_proxy(self) -> Optional[Dict[str, str]]:
        """Возвращает случайный прокси."""
        if not self.proxies:
            return None
        return random.choice(self.proxies)


# Глобальный экземпляр (синглтон)
_proxy_rotator = None


def get_proxy_rotator() -> ProxyRotator:
    global _proxy_rotator
    if _proxy_rotator is None:
        _proxy_rotator = ProxyRotator()
    return _proxy_rotator


def get_proxy_for_account(account_id: int) -> Optional[Dict[str, str]]:
    """Удобная функция для получения прокси по аккаунту."""
    return get_proxy_rotator().get_proxy(account_id)
