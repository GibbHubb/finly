from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:  # F62 — for the type checker only; the mapper resolves the strings
    from app.models.user import User


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)   # 1-12
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="budgets")

    # F45 — one budget per (user, category, month, year), enforced by the DATABASE. The
    # service's SELECT-then-INSERT check stays as the fast path and the friendly 409, but two
    # concurrent POSTs both pass that SELECT; only a constraint makes the rule true.
    __table_args__ = (
        UniqueConstraint("user_id", "category", "month", "year", name="uq_budgets_user_category_period"),
    )
