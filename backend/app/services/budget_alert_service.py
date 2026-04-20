"""Check whether a transaction tips a category over its budget limit."""
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.budget import Budget
from app.models.transaction import Transaction


def check_budget_overspend(
    user_id: int,
    category: str,
    month: int,
    year: int,
    db: Session,
) -> dict | None:
    """Return an alert dict if the user's spend in *category* now exceeds
    the budget limit for *month/year*.  Returns ``None`` otherwise."""

    budget = (
        db.query(Budget)
        .filter(
            Budget.user_id == user_id,
            Budget.category == category,
            Budget.month == month,
            Budget.year == year,
        )
        .first()
    )
    if budget is None:
        return None

    spent: Decimal = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.category == category,
            Transaction.type == "expense",
            func.extract("month", Transaction.transaction_date) == month,
            func.extract("year", Transaction.transaction_date) == year,
        )
        .scalar()
    ) or Decimal("0")

    limit = budget.limit_amount
    if spent > limit:
        return {
            "event": "budget_alert",
            "category": category,
            "spent": str(spent),
            "limit": str(limit),
            "overage": str(spent - limit),
        }
    return None
