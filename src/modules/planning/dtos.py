from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, UUID4, field_validator, model_validator
import re
from src.modules.transactions.dtos import TransactionType
from src.modules.categories.dtos import CategoryResponse

class CreatePlanningEntryDTO(BaseModel):
    title: str
    amount: int
    type: TransactionType
    due_date: date
    category_code: UUID4 | None = None
    description: str | None = None
    installments: int = 1

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

class UpdatePlanningEntryDTO(BaseModel):
    title: str | None = None
    amount: int | None = None
    type: TransactionType | None = None
    due_date: date | None = None
    category_code: UUID4 | None = None
    description: str | None = None
    scope: Literal["this", "this_and_future"] = "this"

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

class PlanningEntryResponse(BaseModel):
    code: UUID4
    title: str
    amount: str
    type: TransactionType
    category: CategoryResponse | None = None
    is_materialized: bool
    materialized_transaction_code: UUID4 | None = None
    due_date: str
    description: str | None = None
    group_code: UUID4 | None = None
    installment_index: int | None = None
    installment_total: int | None = None
    installment_label: str | None = None
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

    @model_validator(mode='after')
    def set_installment_label(self) -> "PlanningEntryResponse":
        if self.installment_index and self.installment_total:
            self.installment_label = f"Parcela {self.installment_index}/{self.installment_total}"
        return self

from pydantic import UUID4

class CategoryHorizonData(BaseModel):
    category_code: UUID4 | None
    category_name: str
    category_color: str | None
    real_income: float
    real_expense: float
    projected_income: float
    projected_expense: float

class PlanningHorizonMonthlyData(BaseModel):
    year_month: str
    categories: list[CategoryHorizonData]
    net_balance: float

class PlanningHorizonResponse(BaseModel):
    horizon: list[PlanningHorizonMonthlyData]
