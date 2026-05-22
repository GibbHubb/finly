from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.models.transaction import Category, TransactionType


class TransactionCreate(BaseModel):
    amount: Decimal
    type: TransactionType
    category: Category
    description: str = ""
    transaction_date: date
    currency: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return v

    @field_validator("currency")
    @classmethod
    def currency_supported(cls, v):
        if v is None:
            return v
        from app.services.rates_service import SUPPORTED_CURRENCIES
        upper = v.upper()
        if upper not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {upper}")
        return upper


class TransactionUpdate(BaseModel):
    amount: Decimal | None = None
    category: Category | None = None
    description: str | None = None
    transaction_date: date | None = None
    currency: str | None = None


class TransactionOut(BaseModel):
    id: int
    amount: Decimal
    type: TransactionType
    category: Category
    description: str
    transaction_date: date
    currency: str
    base_amount: Decimal | None = None
    created_at: datetime
    parent_transaction_id: int | None = None  # F25 — split child rows reference parent

    model_config = {"from_attributes": True}


# F25 — split a transaction into ≥2 children that sum exactly to the parent.
class SplitChildIn(BaseModel):
    amount: Decimal
    category: Category
    description: str = ""

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Split-child amount must be greater than zero")
        return v


class SplitRequest(BaseModel):
    children: list[SplitChildIn]


class CategorySummary(BaseModel):
    category: str
    income: Decimal
    expenses: Decimal
    budget_limit: Decimal | None = None
    budget_remaining: Decimal | None = None


class MonthlySummaryOut(BaseModel):
    month: int
    year: int
    total_income: Decimal
    total_expenses: Decimal
    net: Decimal
    categories: list[CategorySummary]


class ForecastOut(BaseModel):
    month: str          # YYYY-MM
    projected_total: Decimal | None
    confidence: str     # "low" | "medium" | "high"
    data_points_used: int
    reason: str | None = None


class ImportResultOut(BaseModel):
    imported: int
    skipped_duplicates: int
    errors: list[str]


class RecurringItemOut(BaseModel):
    merchant: str
    monthly_amount: float
    typical_day: int
    months_detected: int
    last_seen: date


class MonthlyTrendEntry(BaseModel):
    month: str  # YYYY-MM
    categories: dict[str, Decimal]


class ImportMappingPayload(BaseModel):
    date_col: str
    amount_col: str
    description_col: str
    category_col: str | None = None
    delimiter: str | None = None                     # None → auto-detect
    date_format: str                                 # one of DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, YYYYMMDD
    decimal_format: str                              # "comma" or "dot"


class ImportPreviewOut(BaseModel):
    headers: list[str]
    sample_rows: list[dict[str, str]]
    delimiter: str
    saved_mapping: ImportMappingPayload | None = None
