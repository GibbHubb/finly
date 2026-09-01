from datetime import datetime

from pydantic import BaseModel, Field

from app.models.categorisation_rule import MatchType
from app.models.transaction import Category


class CategorisationRuleCreate(BaseModel):
    match_type: MatchType
    match_value: str = Field(min_length=1, max_length=255)
    category: Category
    priority: int = 100
    enabled: bool = True


class CategorisationRuleUpdate(BaseModel):
    match_type: MatchType | None = None
    match_value: str | None = Field(default=None, min_length=1, max_length=255)
    category: Category | None = None
    priority: int | None = None
    enabled: bool | None = None


class CategorisationRuleOut(BaseModel):
    id: int
    match_type: MatchType
    match_value: str
    category: Category
    priority: int
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RecategoriseResult(BaseModel):
    updated: int
