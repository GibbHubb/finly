from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.transaction import Transaction, TransactionType
from app.models.budget import Budget
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.services.rates_service import convert_amount


def _user_base_currency(user_id: int, db: Session) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    return (user.base_currency if user else "EUR") or "EUR"


def _compute_base_amount(tx: Transaction, base_currency: str, db: Session) -> Decimal | None:
    """Best-effort conversion from tx.amount into the user's base currency."""
    tx_currency = (tx.currency or "EUR").upper()
    if tx_currency == base_currency.upper():
        return Decimal(tx.amount).quantize(Decimal("0.01"))
    return convert_amount(Decimal(tx.amount), tx_currency, base_currency, tx.transaction_date, db)


def create_transaction(data: TransactionCreate, user_id: int, db: Session) -> Transaction:
    base_currency = _user_base_currency(user_id, db)
    payload = data.model_dump()
    if payload.get("currency") is None:
        payload["currency"] = base_currency
    tx = Transaction(**payload, user_id=user_id)
    tx.base_amount = _compute_base_amount(tx, base_currency, db)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def recompute_all_base_amounts(user_id: int, db: Session) -> int:
    """Recompute base_amount for every transaction of `user_id` — called when
    the user changes their base currency. Returns how many rows were updated."""
    base_currency = _user_base_currency(user_id, db)
    txs = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    updated = 0
    for tx in txs:
        new_val = _compute_base_amount(tx, base_currency, db)
        if new_val != tx.base_amount:
            tx.base_amount = new_val
            updated += 1
    if updated:
        db.commit()
    return updated


def get_user_transactions(
    user_id: int,
    db: Session,
    skip: int = 0,
    limit: int = 100,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    tx_type: TransactionType | None = None,
):
    q = db.query(Transaction).filter(Transaction.user_id == user_id)
    if date_from:
        q = q.filter(Transaction.transaction_date >= date_from)
    if date_to:
        q = q.filter(Transaction.transaction_date <= date_to)
    if category:
        q = q.filter(Transaction.category == category)
    if tx_type:
        q = q.filter(Transaction.type == tx_type)
    return q.order_by(Transaction.transaction_date.desc()).offset(skip).limit(limit).all()


def get_monthly_summary(user_id: int, month: int, year: int, db: Session) -> dict:
    """
    Returns total income, total expenses, net, and a per-category breakdown
    that includes spent amount vs. budget limit (if set) for the given month/year.
    """
    # Prefer base_amount (already converted to user's base currency); fall back
    # to amount for pre-F12 rows that were never backfilled.
    amount_expr = func.coalesce(Transaction.base_amount, Transaction.amount)
    rows = (
        db.query(Transaction.category, Transaction.type, func.sum(amount_expr))
        .filter(
            Transaction.user_id == user_id,
            func.strftime("%m", Transaction.transaction_date) == f"{month:02d}",
            func.strftime("%Y", Transaction.transaction_date) == str(year),
        )
        .group_by(Transaction.category, Transaction.type)
        .all()
    )

    budgets = (
        db.query(Budget.category, Budget.limit_amount)
        .filter(Budget.user_id == user_id, Budget.month == month, Budget.year == year)
        .all()
    )
    budget_map: dict[str, Decimal] = {b.category: b.limit_amount for b in budgets}

    category_totals: dict[str, dict] = {}
    total_income = Decimal("0")
    total_expenses = Decimal("0")

    for category, tx_type, total in rows:
        cat_key = category.value if hasattr(category, "value") else str(category)
        if cat_key not in category_totals:
            category_totals[cat_key] = {"income": Decimal("0"), "expenses": Decimal("0")}
        if tx_type == TransactionType.income or tx_type == "income":
            category_totals[cat_key]["income"] += total
            total_income += total
        else:
            category_totals[cat_key]["expenses"] += total
            total_expenses += total

    categories = []
    for cat, totals in category_totals.items():
        entry = {
            "category": cat,
            "income": totals["income"],
            "expenses": totals["expenses"],
        }
        if cat in budget_map:
            entry["budget_limit"] = budget_map[cat]
            entry["budget_remaining"] = budget_map[cat] - totals["expenses"]
        categories.append(entry)

    return {
        "month": month,
        "year": year,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net": total_income - total_expenses,
        "categories": categories,
    }


def get_monthly_category_totals(user_id: int, months: int, db: Session) -> list[dict]:
    """
    Expense totals grouped by (month, category) for the last `months` months,
    zero-filled so empty months still appear in the result. Oldest-first.
    Month keys are 'YYYY-MM' strings.
    """
    today = date.today()
    start_year, start_month = today.year, today.month - (months - 1)
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start = date(start_year, start_month, 1)

    month_expr = func.strftime("%Y-%m", Transaction.transaction_date)
    amount_expr = func.coalesce(Transaction.base_amount, Transaction.amount)
    rows = (
        db.query(
            month_expr.label("month"),
            Transaction.category,
            func.sum(amount_expr).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.expense,
            Transaction.transaction_date >= start,
        )
        .group_by(month_expr, Transaction.category)
        .all()
    )

    skeleton: dict[str, dict[str, Decimal]] = {}
    y, m = start_year, start_month
    for _ in range(months):
        skeleton[f"{y:04d}-{m:02d}"] = {}
        m += 1
        if m > 12:
            m = 1
            y += 1

    for month_key, category, total in rows:
        cat_key = category.value if hasattr(category, "value") else str(category)
        if month_key in skeleton:
            skeleton[month_key][cat_key] = total

    return [{"month": k, "categories": v} for k, v in skeleton.items()]


def update_transaction(tx_id: int, user_id: int, data: TransactionUpdate, db: Session) -> Transaction:
    tx = db.query(Transaction).filter(Transaction.id == tx_id, Transaction.user_id == user_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    payload = data.model_dump(exclude_none=True)
    for field, value in payload.items():
        setattr(tx, field, value)
    if {"amount", "transaction_date"} & payload.keys():
        tx.base_amount = _compute_base_amount(tx, _user_base_currency(user_id, db), db)
    db.commit()
    db.refresh(tx)
    return tx


def delete_transaction(tx_id: int, user_id: int, db: Session) -> None:
    tx = db.query(Transaction).filter(Transaction.id == tx_id, Transaction.user_id == user_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(tx)
    db.commit()
