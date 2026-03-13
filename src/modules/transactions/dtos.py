from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, UUID4, field_validator
from src.modules.categories.dtos import CategoryResponse
import re



class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class CreateTransactionDTO(BaseModel):
    title: str
    amount: int
    type: TransactionType
    due_date: date
    category_code: UUID4 | None = None
    description: str | None = None
    is_paid: bool = False

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v):
        if isinstance(v, str):
            val = re.sub(r"[^\d,]", "", v)
            if not val:
                return 0
            if "," in val:
                parts = val.split(",")
                reals = int(parts[0]) if parts[0] else 0
                cents = int(parts[1][:2].ljust(2, "0"))
                return reals * 100 + cents
            else:
                return int(val) * 100
        elif isinstance(v, (int, float)):
            return int(v * 100)
        return v

    @field_validator("due_date", mode="before")
    @classmethod
    def parse_due_date(cls, v):
        if isinstance(v, str) and "/" in v:
            parts = v.split("/")
            if len(parts) == 3:
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
        return v


class UpdateTransactionDTO(BaseModel):
    title: str | None = None
    amount: int | None = None
    type: TransactionType | None = None
    due_date: date | None = None
    category_code: UUID4 | None = None
    description: str | None = None
    is_paid: bool | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            val = re.sub(r"[^\d,]", "", v)
            if not val:
                return 0
            if "," in val:
                parts = val.split(",")
                reals = int(parts[0]) if parts[0] else 0
                cents = int(parts[1][:2].ljust(2, "0"))
                return reals * 100 + cents
            else:
                return int(val) * 100
        elif isinstance(v, (int, float)):
            return int(v * 100)
        return v

    @field_validator("due_date", mode="before")
    @classmethod
    def parse_due_date(cls, v):
        if v is None:
            return v
        if isinstance(v, str) and "/" in v:
            parts = v.split("/")
            if len(parts) == 3:
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
        return v


class TransactionResponse(BaseModel):
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
