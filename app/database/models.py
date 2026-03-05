from sqlalchemy import JSON, String, Text, Boolean, DateTime, ForeignKey, Integer, Date, BigInteger
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Time  # если нужно хранить время, но для часов достаточно Integer

from datetime import datetime, date
from app.config import settings


engine = create_async_engine(
    f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
    echo=False
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = 'accounts'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text)  # зашифрованный пароль
    cookies: Mapped[dict] = mapped_column(JSON, default={})
    resume_id: Mapped[str] = mapped_column(String(50))  # id резюме на hh
    proxy: Mapped[str] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    telegram_username: Mapped[str] = mapped_column(String(100), nullable=True, default=None)

    # Новые поля для лимитов и расписания
    daily_limit_min: Mapped[int] = mapped_column(Integer, default=50)
    daily_limit_max: Mapped[int] = mapped_column(Integer, default=100)
    response_interval_min: Mapped[int] = mapped_column(Integer, default=120)  # секунды
    response_interval_max: Mapped[int] = mapped_column(Integer, default=480)  # 2-8 минут
    work_start_hour: Mapped[int] = mapped_column(Integer, default=10)  # час начала (мск)
    work_end_hour: Mapped[int] = mapped_column(Integer, default=17)  # час окончания (мск)

    # Поля для лимитов откликов
    daily_response_limit: Mapped[int] = mapped_column(Integer, default=50)   # максимум в день
    responses_today: Mapped[int] = mapped_column(Integer, default=0)         # сколько уже отправлено сегодня
    last_reset_date: Mapped[date] = mapped_column(Date, default=date.today) # дата последнего сброса

    # Фильтр поиска вакансий (например, URL и макс. страниц)
    search_filter: Mapped[dict] = mapped_column(JSON, default={})
    resume_text: Mapped[str] = mapped_column(Text, default="")  # текст резюме

    # Связи
    account_vacancies = relationship("AccountVacancy", back_populates="account", cascade="all, delete-orphan")
    responses = relationship("Response", back_populates="account", cascade="all, delete-orphan")
    invitations = relationship("Invitation", back_populates="account", cascade="all, delete-orphan")

    test_parse_vacancy: Mapped[bool] = mapped_column(Boolean, default=True)
    test_generate_letter: Mapped[bool] = mapped_column(Boolean, default=True)
    test_send_response: Mapped[bool] = mapped_column(Boolean, default=True)
    test_count: Mapped[int] = mapped_column(Integer, default=1)


class Vacancy(Base):
    __tablename__ = 'vacancies'

    id: Mapped[int] = mapped_column(primary_key=True)
    hh_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # id вакансии на hh
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    check_word: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Связи
    account_vacancies = relationship("AccountVacancy", back_populates="vacancy", cascade="all, delete-orphan")
    responses = relationship("Response", back_populates="vacancy", cascade="all, delete-orphan")


class AccountVacancy(Base):
    """Связь аккаунта с вакансией (просмотр/отклик)"""
    __tablename__ = 'account_vacancies'
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('accounts.id'))
    vacancy_id: Mapped[int] = mapped_column(ForeignKey('vacancies.id'), primary_key=True)
    viewed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)   # когда аккаунт увидел вакансию
    responded: Mapped[bool] = mapped_column(Boolean, default=False)        # был ли отправлен отклик
    response_id: Mapped[int] = mapped_column(ForeignKey('responses.id'), nullable=True)  # ссылка на отклик, если есть

    account = relationship("Account", back_populates="account_vacancies")
    vacancy = relationship("Vacancy", back_populates="account_vacancies")
    response = relationship("Response", foreign_keys=[response_id])


class Response(Base):
    __tablename__ = 'responses'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('accounts.id'))
    vacancy_id: Mapped[int] = mapped_column(ForeignKey('vacancies.id'))
    cover_letter: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')  # pending, sent, error
    sent_at: Mapped[datetime] = mapped_column(nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    account = relationship("Account", back_populates="responses")
    vacancy = relationship("Vacancy", back_populates="responses")


class Invitation(Base):
    __tablename__ = 'invitations'

    id: Mapped[int] = mapped_column(primary_key=True)

    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('accounts.id'))
    # vacancy_id: Mapped[int] = mapped_column(ForeignKey('vacancies.id'), primary_key=True)
    vacancy_hh_id: Mapped[str] = mapped_column(String(50))
    company: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, nullable=True)
    invited_at: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    account = relationship("Account", back_populates="invitations")