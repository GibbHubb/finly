from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class TransactionType(str, Enum):
    income = "income"
    expense = "expense"


class Category(str, Enum):
    housing = "housing"
    food = "food"
    transport = "transport"
    entertainment = "entertainment"
    health = "health"
    shopping = "shopping"
    salary = "salary"
    freelance = "freelance"
    other = "other"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    type: Mapped[TransactionType] = mapped_column(String(20), nullable=False)
    category: Mapped[Category] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", server_default="EUR")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    import_hash: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True, index=True)

    owner: Mapped["User"] = relationship(back_populates="transactions")
