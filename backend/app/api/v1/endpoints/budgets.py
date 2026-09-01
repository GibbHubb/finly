from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.budget import BudgetCreate, BudgetOut
from app.services.auth import get_current_user
from app.services.budgets import create_budget, delete_budget, get_user_budgets

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("/", response_model=list[BudgetOut])
def list_budgets(
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List budgets for the authenticated user, optionally filtered by month/year."""
    return get_user_budgets(current_user.id, db, month, year)


@router.post("/", response_model=BudgetOut, status_code=201)
def add_budget(
    data: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a budget limit for a category and month."""
    return create_budget(data, current_user.id, db)


@router.delete("/{budget_id}", status_code=204)
def remove_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a budget."""
    delete_budget(budget_id, current_user.id, db)
