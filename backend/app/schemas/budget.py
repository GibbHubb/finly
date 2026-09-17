from decimal import Decimal
from pydantic import BaseModel, field_validator

from app.models.transaction import Category


class BudgetCreate(BaseModel):
    category: str
    limit_amount: Decimal
    month: int
    year: int

    @field_validator("month")
    @classmethod
    def valid_month(cls, v):
        if not 1 <= v <= 12:
            raise ValueError("Month must be between 1 and 12")
        return v

    # F40 — a budget for "grocerys" was created and then matched no spend, ever: the bar read 0
    # and nothing anywhere looked wrong. Only the categories transactions can have are allowed.
    # Stored as the plain value, the same string the transactions column holds.
    @field_validator("category")
    @classmethod
    def known_category(cls, v):
        try:
            return Category(v.strip().lower()).value
        except ValueError:
            allowed = ", ".join(c.value for c in Category)
            raise ValueError(f"Unknown category '{v}'. Use one of: {allowed}")

    @field_validator("limit_amount")
    @classmethod
    def limit_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Limit must be greater than zero")
        return v

    @field_validator("year")
    @classmethod
    def plausible_year(cls, v):
        if not 2000 <= v <= 2100:
            raise ValueError("Year must be between 2000 and 2100")
        return v


class BudgetOut(BaseModel):
    id: int
    category: str
    limit_amount: Decimal
    month: int
    year: int

    model_config = {"from_attributes": True}
