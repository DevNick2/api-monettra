from datetime import datetime, date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, UUID4, field_validator
import re


class RecurrenceType(str, Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    BIANNUAL = "biannual"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"


class PaymentMethod(str, Enum):
    DEFAULT = "default"
    CREDIT_CARD = "credit_card"


def _parse_amount_str(v) -> int:
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


def _parse_date_br(v) -> date | None:
    """Converte string DD/MM/YYYY para date."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str) and "/" in v:
        parts = v.split("/")
        if len(parts) == 3:
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
    return v


class CreateSubscriptionDTO(BaseModel):
    provider: str
    amount: int
    recurrence: RecurrenceType
    billing_date: date | None = None
    has_trial: bool = False
    is_active: bool = True
    description: str | None = None
    icon_name: str | None = None
    payment_method: PaymentMethod = PaymentMethod.DEFAULT

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v):
        return _parse_amount_str(v)

    @field_validator("billing_date", mode="before")
    @classmethod
    def parse_billing_date(cls, v):
        return _parse_date_br(v)


class UpdateSubscriptionDTO(BaseModel):
    provider: str | None = None
    amount: int | None = None
    recurrence: RecurrenceType | None = None
    billing_date: date | None = None
    has_trial: bool | None = None
    is_active: bool | None = None
    description: str | None = None
    icon_name: str | None = None
    payment_method: PaymentMethod | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v):
        if v is None:
            return v
        return _parse_amount_str(v)

    @field_validator("billing_date", mode="before")
    @classmethod
    def parse_billing_date(cls, v):
        return _parse_date_br(v)


class SubscriptionResponse(BaseModel):
    code: UUID4
    provider: str
    amount: str
    recurrence: RecurrenceType
    billing_date: str | None
    has_trial: bool
    is_active: bool
    description: str | None
    icon_name: str | None
    payment_method: PaymentMethod = PaymentMethod.DEFAULT
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

    @field_validator("billing_date", mode="before") 
    @classmethod
    def format_due_date(cls, v):
        if v is not None:
            if isinstance(v, date):
                return v.strftime("%d/%m/%Y")
            if isinstance(v, str) and "-" in v:
                return date.fromisoformat(v[:10]).strftime("%d/%m/%Y")
            return str(v)
        return None
