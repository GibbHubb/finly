from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.budget import Budget
from app.schemas.budget import BudgetCreate


def create_budget(data: BudgetCreate, user_id: int, db: Session) -> Budget:
    existing = (
        db.query(Budget)
        .filter(
            Budget.user_id == user_id,
            Budget.category == data.category,
            Budget.month == data.month,
            Budget.year == data.year,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Budget for this category/month already exists",
        )
    budget = Budget(**data.model_dump(), user_id=user_id)
    db.add(budget)
    db.commit()
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
