"""F29 — Tag CRUD + tag assignment on transactions.

Tags are user-scoped; same `name` allowed across users. Names are
normalised (lowercased + trimmed) to dedupe casual variants.

F32 note: _resolve_tag and _normalise now delegate to app.services.tags so
that service-layer code can import the helpers without a circular dependency.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tag import Tag
from app.models.transaction import Transaction
from app.models.user import User
from app.services.auth import get_current_user
from app.services.tags import normalise_tag_name, resolve_tag


router = APIRouter(prefix="/tags", tags=["tags"])


class TagOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class TagCreate(BaseModel):
    name: str


def _normalise(name: str) -> str:
    return normalise_tag_name(name)


@router.get("", response_model=list[TagOut])
def list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Tag).filter(Tag.user_id == current_user.id).order_by(Tag.name).all()
    )


@router.post("", response_model=TagOut)
def create_tag(
    body: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = _normalise(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="Tag name is required")
    existing = (
        db.query(Tag)
        .filter(Tag.user_id == current_user.id, Tag.name == name)
        .first()
    )
    if existing:
        return existing
    tag = Tag(user_id=current_user.id, name=name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tag = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == current_user.id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()


def _load_owned_tx(tx_id: int, user_id: int, db: Session) -> Transaction:
    tx = (
        db.query(Transaction)
        .filter(Transaction.id == tx_id, Transaction.user_id == user_id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx


def _resolve_tag(user_id: int, name: str, db: Session) -> Tag:
    """Find-or-create the tag — keeps the assign endpoint single-call.

    Delegates to app.services.tags.resolve_tag (F32: shared helper).
    """
    try:
        return resolve_tag(user_id, name, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/assign/{tx_id}", response_model=list[TagOut])
def assign_tag(
    tx_id: int,
    body: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attach a tag to a transaction (find-or-create the tag by name)."""
    tx = _load_owned_tx(tx_id, current_user.id, db)
    tag = _resolve_tag(current_user.id, body.name, db)
    if tag not in tx.tags:
        tx.tags.append(tag)
    db.commit()
    db.refresh(tx)
    return list(tx.tags)


@router.delete("/assign/{tx_id}/{tag_id}", response_model=list[TagOut])
def unassign_tag(
    tx_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = _load_owned_tx(tx_id, current_user.id, db)
    tx.tags = [t for t in tx.tags if t.id != tag_id]
    db.commit()
    db.refresh(tx)
    return list(tx.tags)
