"""F27 — Stored GoCardless bank connection per finly user.

One row per active requisition. The user can have multiple (different
banks). Status flips to 'error' when GoCardless returns 401 on a sync
(typically a lapsed 90-day consent) so the UI can prompt a reconnect.
Token encryption-at-rest is deliberately out of scope for the sandbox
v1 — tracked as a follow-up.
"""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class BankConnection(Base):
    __tablename__ = "bank_connections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    requisition_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    institution_id: Mapped[str] = mapped_column(String(64), nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")  # pending|active|error
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner = relationship("User")
