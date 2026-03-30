from decimal import Decimal
from pydantic import BaseModel, field_validator


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


class BudgetOut(BaseModel):
    id: int
    category: str
    limit_amount: Decimal
    month: int
    year: int

    model_config = {"from_attributes": True}
