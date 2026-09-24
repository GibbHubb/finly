"""F42 — one row per FAILED login, for the DB-backed lockout counter.

A row is written only on a wrong password (`services/auth.py:login_user`),
never on success and never on an unknown email — so counting is cheap
(`WHERE email = ? AND created_at > now() - 60s`) and the table self-trims:
nothing ever deletes a row, but a real user's failed-attempt history is a
handful of rows, not an unbounded log.

DB-backed, not in-process (e.g. `slowapi`'s default memory store): finly
runs as a Vercel serverless function, one container per concurrent request,
so an in-process counter resets on every cold start. A limiter that cannot
count is worse than none — it looks like protection.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
