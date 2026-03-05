# hh_client/models.py
"""Pydantic модели для структурирования ответов hh.ru."""

from typing import Optional, List
from pydantic import BaseModel, Field


class Salary(BaseModel):
    """Зарплата в вакансии."""
    from_: Optional[int] = Field(None, alias="from")
    to: Optional[int] = None
    currency: Optional[str] = None
    gross: Optional[bool] = None


class VacancyPreview(BaseModel):
    """Краткая информация о вакансии из списка поиска."""
    id: int = Field(alias="vacancyId")
    title: str = Field(alias="name")
    url: Optional[str] = Field(None, alias="link")
    has_test: bool = Field(alias="userTestPresent")
    response_letter_required: bool = Field(alias="@responseLetterRequired")
    salary: Optional[Salary] = None
    employer: Optional[str] = None  # можно добавить, если понадобится

    class Config:
        populate_by_name = True


class VacancyDetails(BaseModel):
    """Детальная информация о вакансии."""
    description: str
    skills: List[str] = []
    full_html: Optional[str] = None  # если нужно сохранять сырой HTML


class ApplyResult(BaseModel):
    """Результат отправки отклика."""
    success: bool
    error: Optional[str] = None
    limit_exceeded: bool = False  # флаг для ошибки negotiations-limit-exceeded
