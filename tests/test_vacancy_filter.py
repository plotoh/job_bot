from app.services.vacancy_filter import extract_secret_word, is_backend_python_keywords


def test_extract_secret_word_found():
    desc = "Укажите слово 'python' в отклике."
    assert extract_secret_word(desc) == "python"


def test_extract_secret_word_not_found():
    desc = "Просто описание"
    assert extract_secret_word(desc) is None


def test_is_backend_python_keywords_true():
    title = "Python Backend Developer"
    desc = "Требуется опыт работы с Django."
    assert is_backend_python_keywords(title, desc) is True


def test_is_backend_python_keywords_fullstack_excluded():
    title = "Fullstack Python Developer"
    desc = "Работа с Django и React"
    assert is_backend_python_keywords(title, desc) is False  # из-за fullstack в названии


def test_is_backend_python_keywords_frontend_excluded():
    title = "Frontend Developer"
    desc = "Знание Python приветствуется"
    assert is_backend_python_keywords(title, desc) is False
