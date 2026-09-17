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


# ---------------------------------------------------------------------------
# F35/F53 — alerts on CROSSING a limit, for every write that moves spend
# ---------------------------------------------------------------------------
# An alert means "this change pushed the category over its budget": spend was at or under the
# limit before the write and is over it after. "Currently over" is not an alert: a toast for a
# budget that was already over before the change is a notification about the past.

SpendKey = tuple[str, int, int]  # (category, month, year)


def _category_value(category) -> str:
    return getattr(category, "value", category)


def spend_key(category, on_date) -> SpendKey:
    return (_category_value(category), on_date.month, on_date.year)


def snapshot_spend(user_id: int, keys, db: Session) -> dict[SpendKey, Decimal]:
    """Current spend for each (category, month, year) that has a budget. Keys without a budget
    are skipped: nothing can be crossed there."""
    out: dict[SpendKey, Decimal] = {}
    for cat, month, year in set(keys):
        has_budget = db.query(Budget.id).filter(
            Budget.user_id == user_id, Budget.category == cat, Budget.month == month, Budget.year == year,
        ).first()
        if has_budget:
            out[(cat, month, year)] = category_spend(user_id, cat, month, year, db)
    return out


def crossed_alerts(user_id: int, before: dict[SpendKey, Decimal], db: Session) -> list[dict]:
    """Alerts for each budgeted key whose spend went from <= limit (before) to > limit (now)."""
    alerts = []
    for (cat, month, year), was in sorted(before.items()):
        budget = db.query(Budget).filter(
            Budget.user_id == user_id, Budget.category == cat, Budget.month == month, Budget.year == year,
        ).first()
        if budget is None:
            continue
        now = category_spend(user_id, cat, month, year, db)
        if was <= budget.limit_amount < now:
            alerts.append({
                "event": "budget_alert", "category": cat, "month": month, "year": year,
                "spent": str(now), "limit": str(budget.limit_amount), "overage": str(now - budget.limit_amount),
            })
    return alerts
