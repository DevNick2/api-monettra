from datetime import date, datetime
from uuid import UUID

import re
from pydantic import BaseModel, UUID4, field_validator


def _parse_amount(v) -> int:
    """Converte string pt-BR ou número para centavos."""
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
    elif isinstance(v, float):
        return int(v * 100)
    elif isinstance(v, int):
        return v
    return v


def _format_amount(cents: int) -> str:
    reais = cents // 100
    centavos = cents % 100
    reais_str = f"{reais:,}".replace(",", ".")
    return f"{reais_str},{centavos:02d}"


# ─── Credit Card DTOs ──────────────────────────────────────────────────────────

class CreateCreditCardDTO(BaseModel):
    name: str
    credit_limit: int
    closing_day: int
    due_day: int

    @field_validator("credit_limit", mode="before")
    @classmethod
    def parse_limit(cls, v):
        return _parse_amount(v)

    @field_validator("closing_day", "due_day", mode="before")
    @classmethod
    def validate_day(cls, v):
        v = int(v)
        if not (1 <= v <= 31):
            raise ValueError("O dia deve estar entre 1 e 31")
        return v


class UpdateCreditCardDTO(BaseModel):
    name: str | None = None
    credit_limit: int | None = None
    closing_day: int | None = None
    due_day: int | None = None

    @field_validator("credit_limit", mode="before")
    @classmethod
    def parse_limit(cls, v):
        if v is None:
            return v
        return _parse_amount(v)

    @field_validator("closing_day", "due_day", mode="before")
    @classmethod
    def validate_day(cls, v):
        if v is None:
            return v
        v = int(v)
        if not (1 <= v <= 31):
            raise ValueError("O dia deve estar entre 1 e 31")
        return v


class CreditCardResponse(BaseModel):
    code: UUID4
    name: str
    credit_limit: str
    closing_day: int
    due_day: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("credit_limit", mode="before")
    @classmethod
    def format_limit(cls, v):
        return _format_amount(int(v))


# ─── Credit Card Charge DTOs ───────────────────────────────────────────────────

class CreateCreditCardChargeDTO(BaseModel):
    """Lançamento no cartão de crédito — suporta parcelamento."""
    title: str
    amount: int
    purchase_date: date
    credit_card_code: UUID4
    installments: int = 1
    category_code: UUID4 | None = None
    description: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v):
        return _parse_amount(v)

    @field_validator("purchase_date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str) and "/" in v:
            parts = v.split("/")
            if len(parts) == 3:
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
        return v

    @field_validator("installments", mode="before")
    @classmethod
    def validate_installments(cls, v):
        v = int(v)
        if v < 1:
            raise ValueError("Parcelas deve ser >= 1")
        return v


# ─── Invoice DTOs ──────────────────────────────────────────────────────────────

class InvoiceTransactionItem(BaseModel):
    code: UUID4
    title: str
    amount: str
    due_date: str
    is_paid: bool
    description: str | None
    installment_label: str | None = None

    model_config = {"from_attributes": True}

    @field_validator("amount", mode="before")
    @classmethod
    def format_amount(cls, v):
        return _format_amount(int(v))

    @field_validator("due_date", mode="before")
    @classmethod
    def format_due_date(cls, v):
        if isinstance(v, date):
            return v.strftime("%d/%m/%Y")
        if isinstance(v, str) and "-" in v:
            return date.fromisoformat(v[:10]).strftime("%d/%m/%Y")
        return str(v)


class InvoiceResponse(BaseModel):
    code: UUID4
    reference_month: int
    reference_year: int
    total_amount: str
    is_paid: bool
    credit_card_code: UUID4
    credit_card_name: str
    transactions: list[InvoiceTransactionItem] = []
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("total_amount", mode="before")
    @classmethod
    def format_total(cls, v):
        return _format_amount(int(v))
