from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.transaction import Category


class MatchType(str, Enum):
    contains = "contains"
    equals = "equals"
    starts_with = "starts_with"
    regex = "regex"


class CategorisationRule(Base):
    """A user-defined rule that maps transaction descriptions to a category."""

    __tablename__ = "categorisation_rules"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    match_type: Mapped[MatchType] = mapped_column(String(20), nullable=False)
    match_value: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[Category] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
