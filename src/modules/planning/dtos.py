from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, UUID4, field_validator, model_validator
import re
from src.modules.transactions.dtos import TransactionType
from src.modules.categories.dtos import CategoryResponse

class PlanningEntryResponse(BaseModel):
    code: UUID4
    title: str
    amount: str
    type: TransactionType
    category: CategoryResponse | None
    is_paid: bool
    paid_at: datetime | None
    due_date: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("amount", mode="before")
    @classmethod
    def format_amount(cls, v):
        cents = int(v) if v is not None else 0
        reais = cents // 100
        centavos = cents % 100
        reais_str = f"{reais:,}".replace(",", ".")
        return f"{reais_str},{centavos:02d}"

    @field_validator("due_date", mode="before")
    @classmethod
    def format_due_date(cls, v):
        if isinstance(v, date):
            return v.strftime("%d/%m/%Y")
        if isinstance(v, str) and "-" in v:
            return date.fromisoformat(v[:10]).strftime("%d/%m/%Y")
        return str(v)