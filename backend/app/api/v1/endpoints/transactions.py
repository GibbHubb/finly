from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.transaction import Category, TransactionType
from app.models.user import User
from app.schemas.transaction import (
    MonthlySummaryOut,
    TransactionCreate,
    TransactionOut,
    TransactionUpdate,
)
from app.services.auth import get_current_user
from app.services.transactions import (
    create_transaction,
    delete_transaction,
    get_monthly_summary,
    get_user_transactions,
    update_transaction,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/summary", response_model=MonthlySummaryOut)
def monthly_summary(
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    year: int = Query(..., ge=2000, description="4-digit year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Monthly summary: total income, total expenses, net balance, and per-category
    breakdown with budget limit and remaining if a budget is set.
    """
    return get_monthly_summary(current_user.id, month, year, db)


@router.get("/", response_model=list[TransactionOut])
def list_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    date_from: date | None = Query(None, description="Filter from date (inclusive), e.g. 2024-01-01"),
    date_to: date | None = Query(None, description="Filter to date (inclusive), e.g. 2024-12-31"),
    category: Category | None = Query(None, description="Filter by category"),
    type: TransactionType | None = Query(None, description="Filter by type: income or expense"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List transactions for the authenticated user with optional filters."""
    return get_user_transactions(
        current_user.id, db, skip, limit,
        date_from=date_from,
        date_to=date_to,
        category=category.value if category else None,
        tx_type=type,
    )


@router.post("/", response_model=TransactionOut, status_code=201)
def add_transaction(
    data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new income or expense transaction."""
    return create_transaction(data, current_user.id, db)


@router.patch("/{tx_id}", response_model=TransactionOut)
def edit_transaction(
    tx_id: int,
    data: TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partially update an existing transaction."""
    return update_transaction(tx_id, current_user.id, data, db)


@router.delete("/{tx_id}", status_code=204)
def remove_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a transaction."""
    delete_transaction(tx_id, current_user.id, db)
