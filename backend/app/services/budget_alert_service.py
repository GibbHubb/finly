"""Check whether a transaction tips a category over its budget limit."""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.budget import Budget
from app.services.transactions import category_spend  # F39 — one shared spend calculator


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

    # F39 — was a second, wrong copy of the spend sum here (raw `amount`, split parents
    # double-counted). Now the single shared calculator, so this alert and the Budgets
    # bar always agree.
    spent: Decimal = category_spend(user_id, category, month, year, db)

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
