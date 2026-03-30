from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.transaction import Transaction
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
