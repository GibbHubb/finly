from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.transaction import Transaction, TransactionType
from app.models.budget import Budget
from app.schemas.transaction import TransactionCreate, TransactionUpdate


def create_transaction(data: TransactionCreate, user_id: int, db: Session) -> Transaction:
    tx = Transaction(**data.model_dump(), user_id=user_id)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def get_user_transactions(user_id: int, db: Session, skip: int = 0, limit: int = 100):
    return (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.transaction_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_monthly_summary(user_id: int, month: int, year: int, db: Session) -> dict:
    """
    Returns total income, total expenses, net, and a per-category breakdown
    that includes spent amount vs. budget limit (if set) for the given month/year.
    """
    rows = (
        db.query(Transaction.category, Transaction.type, func.sum(Transaction.amount))
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


def update_transaction(tx_id: int, user_id: int, data: TransactionUpdate, db: Session) -> Transaction:
    tx = db.query(Transaction).filter(Transaction.id == tx_id, Transaction.user_id == user_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(tx, field, value)
    db.commit()
    db.refresh(tx)
    return tx


def delete_transaction(tx_id: int, user_id: int, db: Session) -> None:
    tx = db.query(Transaction).filter(Transaction.id == tx_id, Transaction.user_id == user_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(tx)
    db.commit()
