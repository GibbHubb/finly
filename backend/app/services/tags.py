"""Shared tag-service helpers (F32).

Promoted from app/api/v1/endpoints/tags.py so that service-layer code
(e.g. recurring_service) can import _resolve_tag without creating a
circular import (service → endpoint → service).

The endpoint module re-imports from here; its public API is unchanged.
"""

from sqlalchemy.orm import Session

from app.models.tag import Tag


def normalise_tag_name(name: str) -> str:
    """Lowercase + strip.  Identical to the logic in the tags endpoint."""
    return (name or "").strip().lower()


def resolve_tag(user_id: int, name: str, db: Session) -> Tag:
    """Find-or-create a user-scoped tag by name (case-insensitive).

    Flushes but does NOT commit — the caller owns the transaction boundary.
    Raises ValueError when *name* is blank after normalisation.
    """
    norm = normalise_tag_name(name)
    if not norm:
        raise ValueError("Tag name must not be empty")
    tag = db.query(Tag).filter(Tag.user_id == user_id, Tag.name == norm).first()
    if tag:
        return tag
    tag = Tag(user_id=user_id, name=norm)
    db.add(tag)
    db.flush()
    return tag
