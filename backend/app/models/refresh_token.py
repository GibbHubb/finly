"""F42 — one row per issued session (access + refresh pair share a `jti`).

`jti` is minted at login/refresh and embedded in BOTH the access token
(`typ=access`) and the refresh token (`typ=refresh`) JWTs. This row is the
server-side revocation record for that `jti`: `get_current_user` looks it up
on every request and rejects anything whose row is missing or `revoked_at`
is set — that is how a logout kills an already-issued access token before
its own 15-minute expiry, not just the refresh token.

`token_hash` stores sha256(refresh JWT), never the token itself: the JWT's
signature already makes it unforgeable, but a DB read (or a leaked backup)
should not hand out a bearer token good for 14 days.

`replaced_by` is the new `jti` a rotation issued. On `/auth/refresh`,
presenting a token whose row has `revoked_at` already set (a replay of a
consumed token) revokes the **whole chain** for that user — the standard
response to a stolen refresh token — not just this one row.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    replaced_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner = relationship("User")
