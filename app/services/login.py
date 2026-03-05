import logging
import re

import requests
from typing import Dict

logger = logging.getLogger(__name__)


def login_and_get_cookies(username: str, password: str) -> Dict[str, str]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    })

    resp = session.get("https://hh.ru/account/login")
    xsrf_match = re.search(r'name="_xsrf" value="([^"]+)"', resp.text)
    if not xsrf_match:
        raise Exception("Could not extract _xsrf token")
    xsrf = xsrf_match.group(1)

    login_data = {
        "_xsrf": xsrf,
        "backUrl": "https://hh.ru/",
        "username": username,
        "password": password,
        "action": "Войти",
    }
    resp = session.post("https://hh.ru/account/login", data=login_data, allow_redirects=False)

    # Логируем ответ для отладки
    logger.error(f"Login response status: {resp.status_code}")
    logger.error(f"Login response headers: {resp.headers}")
    logger.error(f"Login response body (first 500 chars): {resp.text[:500]}")

    if resp.status_code == 302 and resp.headers.get("Location") == "https://hh.ru/":
        cookies = session.cookies.get_dict()
        logger.info("Login successful")
        return cookies
    else:
        raise Exception("Login failed")