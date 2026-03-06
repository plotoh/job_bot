import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from aioresponses import aioresponses

from hh_client import HHClient, HHAuthError, HHNetworkError
from hh_client.models import VacancyPreview


@pytest.mark.asyncio
async def test_search_vacancies_success():
    """Тест успешного поиска вакансий."""
    cookies = {"_xsrf": "abc123"}
    client = HHClient(cookies)

    # Мокаем ответ от сервера
    with aioresponses() as mocked:
        mocked.get(
            "https://hh.ru/search/vacancy?text=python&page=0",
            status=200,
            body=''',"vacancies":[{"vacancyId": 123, "name": "Python Dev", "links": {"desktop": "https://hh.ru/vacancy/123"}, "userTestPresent": false, "@responseLetterRequired": false}]'''
        )
        # Нам нужно, чтобы клиент создал сессию; вызовем _create_session вручную или через __aenter__
        await client._create_session()
        try:
            vacancies = await client.search_vacancies("https://hh.ru/search/vacancy?text=python", max_pages=1)
            assert len(vacancies) == 1
            assert vacancies[0].id == 123
            assert vacancies[0].title == "Python Dev"
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_search_vacancies_auth_error():
    """Тест ошибки авторизации (401)."""
    cookies = {"_xsrf": "abc123"}
    client = HHClient(cookies)

    with aioresponses() as mocked:
        mocked.get(
            "https://hh.ru/search/vacancy?text=python&page=0",
            status=401
        )
        await client._create_session()
        with pytest.raises(HHAuthError):
            await client.search_vacancies("https://hh.ru/search/vacancy?text=python", max_pages=1)
        await client.close()


@pytest.mark.asyncio
async def test_apply_with_test():
    """Тест отправки отклика с тестом."""
    cookies = {"_xsrf": "abc123"}
    client = HHClient(cookies)

    # Мокаем получение тестов и отправку
    with aioresponses() as mocked:
        # Мок для get_vacancy_tests
        mocked.get(
            "https://hh.ru/applicant/vacancy_response?vacancyId=123&startedWithQuestion=false",
            status=200,
            body=''',"vacancyTests":{"123":{"uidPk":"uid","guid":"guid","startTime":"now","required":true,"tasks":[{"id":1,"candidateSolutions":[{"id":10}]}]}}'''
        )
        # Мок для отправки отклика
        mocked.post(
            "https://hh.ru/applicant/vacancy_response/popup",
            status=200,
            payload={"success": True}
        )
        await client._create_session()
        result = await client.apply(123, "resume_hash", "Hello")
        assert result.success is True
        await client.close()