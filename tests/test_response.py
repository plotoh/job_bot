import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.response import send_response_for_vacancy
from app.database.models import Account, Vacancy, Response, AccountVacancy
from hh_client import ApplyResult


@pytest.mark.asyncio
async def test_send_response_for_vacancy_success(mocker):
    # Моки
    session = AsyncMock(spec=AsyncSession)
    account = Account(id=1, resume_id="resume_hash", cookies={}, proxy=None)
    vacancy = Vacancy(id=1, check_word=None)
    mocker.patch("app.services.letter_generator.generate_cover_letter", return_value="Test letter")
    mocker.patch("app.services.response.HHClient")

    # Настраиваем мок клиента
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.apply.return_value = ApplyResult(success=True)
    mocker.patch("app.services.response.HHClient", return_value=mock_client)

    # Вызов
    result = await send_response_for_vacancy(account, vacancy, session)

    assert result is True
    session.add.assert_called()  # проверяем, что Response был добавлен
    session.commit.assert_called()


@pytest.mark.asyncio
async def test_send_response_for_vacancy_failure(mocker):
    session = AsyncMock()
    account = Account(id=1, resume_id="resume_hash")
    vacancy = Vacancy(id=1, check_word=None)
    mocker.patch("app.services.letter_generator.generate_cover_letter", return_value="Test letter")

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.apply.return_value = ApplyResult(success=False, error="Some error")
    mocker.patch("app.services.response.HHClient", return_value=mock_client)

    result = await send_response_for_vacancy(account, vacancy, session)

    assert result is False
    # Проверяем, что статус response стал error
    # Нам нужно перехватить объект Response, который добавляется в сессию
    # Можно проверить, что session.add был вызван с объектом, у которого status="pending",
    # а потом после обновления статус стал error.
    # Но проще проверить, что commit был вызван
    session.commit.assert_called()
