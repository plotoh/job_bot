from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, Integer, JSON
from datetime import datetime
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

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text)  # зашифрованный пароль
    cookies: Mapped[dict] = mapped_column(JSON, default={})
    resume_id: Mapped[str] = mapped_column(String(50))  # id резюме на hh
    proxy: Mapped[str] = mapped_column(String(200), nullable=True)  # конкретный прокси для аккаунта или пул
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # связи
    vacancies = relationship("Vacancy", back_populates="account")
    responses = relationship("Response", back_populates="account")
    invitations = relationship("Invitation", back_populates="account")

    search_filter: Mapped[dict] = mapped_column(JSON,
                                                default={})  # например, {"url": "https://hh.ru/search/vacancy?text=Python&area=1", "max_pages": 1}
    resume_text: Mapped[str] = mapped_column(Text, default="")  # текст резюме


class Vacancy(Base):
    __tablename__ = 'vacancies'

    id: Mapped[int] = mapped_column(primary_key=True)
    hh_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # id вакансии на hh
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    check_word: Mapped[str] = mapped_column(String(200), nullable=True)
    has_response: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    account = relationship("Account", back_populates="vacancies")
    responses = relationship("Response", back_populates="vacancy")


class Response(Base):
    __tablename__ = 'responses'

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
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
    account_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    vacancy_hh_id: Mapped[str] = mapped_column(String(50))
    company: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, nullable=True)
    invited_at: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    account = relationship("Account", back_populates="invitations")
