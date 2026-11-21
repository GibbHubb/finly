from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:  # F62 — for the type checker only; the mapper resolves the strings
    from app.models.budget import Budget
    from app.models.savings_goal import SavingsGoal
    from app.models.transaction import Transaction


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR", server_default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    savings_goals: Mapped[list["SavingsGoal"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


# F64 — one account per email whatever its case. Login and registration match on
# lower(email) (services/auth.py), and this index is what makes "at most one row
# matches" true under concurrent registrations, not just on the happy path.
# Declared here (not only in the migration) so create_all and `alembic check` agree.
Index("ix_users_email_lower", func.lower(User.email), unique=True)
