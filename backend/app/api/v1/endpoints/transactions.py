from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionOut, TransactionUpdate
from app.services.auth import get_current_user
from app.services.transactions import (
    create_transaction,
    delete_transaction,
    get_user_transactions,
    update_transaction,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/", response_model=list[TransactionOut])
def list_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all transactions for the authenticated user."""
    return get_user_transactions(current_user.id, db, skip, limit)


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
