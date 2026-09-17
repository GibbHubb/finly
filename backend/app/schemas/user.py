from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    # F40 — "" was a valid password. 8 is a floor, not a strength policy.
    password: str = Field(min_length=8)
    full_name: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    base_currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: str | None = None
    base_currency: str | None = None
    current_password: str | None = None
    # F40 — the same floor as registration; otherwise a password change could set "".
    new_password: str | None = Field(default=None, min_length=8)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: int | None = None
