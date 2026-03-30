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

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return v


class TransactionUpdate(BaseModel):
    amount: Decimal | None = None
    category: Category | None = None
    description: str | None = None
    transaction_date: date | None = None


class TransactionOut(BaseModel):
    id: int
    amount: Decimal
    type: TransactionType
    category: Category
    description: str
    transaction_date: date
    created_at: datetime

    model_config = {"from_attributes": True}
