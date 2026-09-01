from datetime import date
from decimal import Decimal

from pydantic import BaseModel, field_validator


class SavingsGoalCreate(BaseModel):
    name: str
    target_amount: Decimal
    deadline: date | None = None

    @field_validator("target_amount")
    @classmethod
    def target_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Target amount must be greater than zero")
        return v


class SavingsGoalUpdate(BaseModel):
    name: str | None = None
    target_amount: Decimal | None = None
    current_amount: Decimal | None = None
    deadline: date | None = None


class SavingsGoalOut(BaseModel):
    id: int
    name: str
    target_amount: Decimal
    current_amount: Decimal
    deadline: date | None
    progress_pct: float

    model_config = {"from_attributes": True}
