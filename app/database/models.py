from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    JSON, String, Text, Boolean, DateTime, ForeignKey,
    Integer, Date, BigInteger, UniqueConstraint, Table, Column
)
from sqlalchemy.ext.asyncio import (
    AsyncAttrs, async_sessionmaker, create_async_engine
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings

# ==================== Настройка движка и сессии ====================

engine = create_async_engine(
    f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@"
    f"{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}",
    echo=False
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# ==================== Базовый класс ====================

class Base(AsyncAttrs, DeclarativeBase):
    pass


# Таблица для связи многие-ко-многим (пользователи и каналы)
user_channels = Table(
    'user_channels',
    Base.metadata,
    Column('user_id', BigInteger, ForeignKey('accounts.id'), primary_key=True),
    Column('channel_id', BigInteger, ForeignKey('telegram_channels.id'), primary_key=True)
)


# ==================== Модель аккаунта пользователя ====================

class Account(Base):
    __tablename__ = 'accounts'

    # --- Основные данные аккаунта ---
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text)
    cookies: Mapped[dict] = mapped_column(JSON, default={})
    resume_id: Mapped[str] = mapped_column(String(50))
    proxy: Mapped[str] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    telegram_username: Mapped[str] = mapped_column(String(100), nullable=True, default=None)
    cookies_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    letter_template: Mapped[str] = mapped_column(Text, default=settings.DEFAULT_LETTER_TEMPLATE)

    # --- Настройки лимитов и расписания ---
    daily_limit_min: Mapped[int] = mapped_column(Integer, default=53)
    daily_limit_max: Mapped[int] = mapped_column(Integer, default=137)
    response_interval_min: Mapped[int] = mapped_column(Integer, default=120)
    response_interval_max: Mapped[int] = mapped_column(Integer, default=480)
    work_start_hour: Mapped[int] = mapped_column(Integer, default=10)
    work_end_hour: Mapped[int] = mapped_column(Integer, default=17)

    # --- Статистика откликов за день ---
    daily_response_limit: Mapped[int] = mapped_column(Integer, default=50)
    responses_today: Mapped[int] = mapped_column(Integer, default=0)
    last_reset_date: Mapped[date] = mapped_column(Date, default=date.today)

    # --- Параметры поиска вакансий ---
    search_filter: Mapped[dict] = mapped_column(JSON, default={})
    max_pages: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    resume_text: Mapped[str] = mapped_column(Text, default="")

    # --- Настройки тестового режима ---
    test_parse_vacancy: Mapped[bool] = mapped_column(Boolean, default=True)
    test_generate_letter: Mapped[bool] = mapped_column(Boolean, default=True)
    test_send_response: Mapped[bool] = mapped_column(Boolean, default=True)
    test_count: Mapped[int] = mapped_column(Integer, default=1)

    # --- Связи ---
    account_vacancies = relationship("AccountVacancy", back_populates="account", cascade="all, delete-orphan")
    responses = relationship("Response", back_populates="account", cascade="all, delete-orphan")
    invitations = relationship("Invitation", back_populates="account", cascade="all, delete-orphan")
    daily_stats = relationship("DailyStats", back_populates="account", cascade="all, delete-orphan")
    channels = relationship("TelegramChannel", secondary=user_channels, back_populates="users")


# ==================== Модель вакансии ====================

class Vacancy(Base):
    __tablename__ = 'vacancies'

    id: Mapped[int] = mapped_column(primary_key=True)
    hh_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    check_word: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # --- Связи ---
    account_vacancies = relationship("AccountVacancy", back_populates="vacancy", cascade="all, delete-orphan")
    responses = relationship("Response", back_populates="vacancy", cascade="all, delete-orphan")


# ==================== Связь аккаунта с вакансией ====================

class AccountVacancy(Base):
    __tablename__ = 'account_vacancies'

    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('accounts.id'))
    vacancy_id: Mapped[int] = mapped_column(ForeignKey('vacancies.id'), primary_key=True)
    viewed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    responded: Mapped[bool] = mapped_column(Boolean, default=False)
    response_id: Mapped[int] = mapped_column(ForeignKey('responses.id'), nullable=True)

    # --- Связи ---
    account = relationship("Account", back_populates="account_vacancies")
    vacancy = relationship("Vacancy", back_populates="account_vacancies")
    response = relationship("Response", foreign_keys=[response_id])


# ==================== Модель ежедневной статистики ====================

class DailyStats(Base):
    __tablename__ = 'daily_stats'

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('accounts.id'), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    responses_count: Mapped[int] = mapped_column(Integer, default=0)
    invitations_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Уникальность (account_id, date)
    __table_args__ = (
        UniqueConstraint('account_id', 'date', name='uq_daily_stats_account_date'),
    )

    account = relationship("Account", back_populates="daily_stats")


# ==================== Модель отклика ====================

class Response(Base):
    __tablename__ = 'responses'

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('accounts.id'))
    vacancy_id: Mapped[int] = mapped_column(ForeignKey('vacancies.id'))
    cover_letter: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    sent_at: Mapped[datetime] = mapped_column(nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # --- Связи ---
    account = relationship("Account", back_populates="responses")
    vacancy = relationship("Vacancy", back_populates="responses")


# ==================== Модель приглашения ====================

class Invitation(Base):
    __tablename__ = 'invitations'

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('accounts.id'))
    vacancy_hh_id: Mapped[str] = mapped_column(String(50))
    company: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, nullable=True)
    invited_at: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # --- Связи ---
    account = relationship("Account", back_populates="invitations")


class TelegramChannel(Base):
    __tablename__ = 'telegram_channels'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # chat_id канала
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    invite_link: Mapped[Optional[str]] = mapped_column(String(500))  # ссылка-приглашение (если нужно)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Связь с пользователями (кто имеет доступ)
    users = relationship("Account", secondary=user_channels, back_populates="channels")


class ChannelVacancy(Base):
    __tablename__ = 'channel_vacancies'

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('telegram_channels.id'), nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # id сообщения в канале
    text: Mapped[str] = mapped_column(Text)  # полный текст сообщения
    published_at: Mapped[datetime] = mapped_column(DateTime)  # дата публикации
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_parsed: Mapped[bool] = mapped_column(Boolean, default=False)  # обработано ли (для выдачи)

    # Индекс для быстрого поиска новых сообщений
    __table_args__ = (
        UniqueConstraint('channel_id', 'message_id', name='uq_channel_message'),
    )
