import pytest
from app.services.letter_generator import rand_text, generate_cover_letter
from app.database.models import Account, Vacancy
from app.config import settings


def test_rand_text_simple():
    text = "Hello {world|there}"
    result = rand_text(text)
    assert result in ["Hello world", "Hello there"]


def test_rand_text_nested():
    text = "{Hello|Hi} {world|{there|everyone}}"
    result = rand_text(text)
    # Не проверяем конкретное значение, просто что нет фигурных скобок
    assert "{" not in result
    assert "}" not in result


@pytest.mark.asyncio
async def test_generate_cover_letter():
    account = Account(
        id=1,
        telegram_username="@testuser",
        letter_template="{secret_word_phrase}\nHello {vacancy_name} from {tg_username}"
    )
    vacancy = Vacancy(id=1, title="Python Developer", check_word=None)
    letter = await generate_cover_letter(account, vacancy, "secret123")
    assert "Проверочное слово: secret123" in letter
    assert "Hello Python Developer" in letter
    assert "@testuser" in letter


@pytest.mark.asyncio
async def test_generate_cover_letter_no_tg():
    account = Account(
        id=1,
        telegram_username=None,
        letter_template="{tg_username}\n{Мой телеграм|tg}: {tg_username}"
    )
    vacancy = Vacancy(id=1, title="Test", check_word=None)
    letter = await generate_cover_letter(account, vacancy)
    # Строки с упоминанием Telegram должны быть удалены
    assert "Мой телеграм:" not in letter
    assert "tg:" not in letter
    assert letter.strip() == ""  # После удаления может остаться пустая строка
