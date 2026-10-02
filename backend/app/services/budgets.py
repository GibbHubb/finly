from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.budget import Budget
from app.schemas.budget import BudgetCreate

DUPLICATE_BUDGET = "Budget for this category/month already exists"


def _find_existing(data: BudgetCreate, user_id: int, db: Session) -> Budget | None:
    return (
        db.query(Budget)
        .filter(
            Budget.user_id == user_id,
            Budget.category == data.category,
            Budget.month == data.month,
            Budget.year == data.year,
        )
        .first()
    )


def create_budget(data: BudgetCreate, user_id: int, db: Session) -> Budget:
    # The SELECT is the fast path and the friendly message. It is NOT the rule: two concurrent
    # POSTs both pass it. F45 — `uq_budgets_user_category_period` is the rule, and losing that
    # race returns the same 409 instead of a second budget (or a 500).
    if _find_existing(data, user_id, db):
        raise HTTPException(status_code=409, detail=DUPLICATE_BUDGET)
    budget = Budget(**data.model_dump(), user_id=user_id)
    db.add(budget)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=DUPLICATE_BUDGET)
    db.refresh(budget)
    return budget


def get_user_budgets(user_id: int, db: Session, month: int | None = None, year: int | None = None):
    q = db.query(Budget).filter(Budget.user_id == user_id)
    if month is not None:
        q = q.filter(Budget.month == month)
    if year is not None:
        q = q.filter(Budget.year == year)
    return q.order_by(Budget.year.desc(), Budget.month.desc()).all()


def delete_budget(budget_id: int, user_id: int, db: Session) -> None:
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == user_id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()
