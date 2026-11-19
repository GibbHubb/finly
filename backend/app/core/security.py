import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# F61 — tolerated clock skew between the instance that minted a token and the one reading it.
JWT_LEEWAY_SECONDS = 10


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def new_jti() -> str:
    """A fresh, unguessable session id — shared by an access/refresh pair.

    F42: this is the value both tokens carry and the value `refresh_tokens`
    is keyed on, so revoking the row kills BOTH tokens at once.
    """
    return secrets.token_hex(16)


def hash_token(token: str) -> str:
    """sha256 hex digest — what gets stored, never the token itself (F42)."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(subject: Any, jti: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": str(subject), "iat": now, "exp": expire, "jti": jti, "typ": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: Any, jti: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    payload = {"sub": str(subject), "iat": now, "exp": expire, "jti": jti, "typ": "refresh"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        # F61 — PyJWT validates `iat` (python-jose did not). A token minted by another serverless
        # instance whose clock runs a few seconds ahead would otherwise be "not yet valid" -> 401.
        # F63 — PyJWT only checks `exp` IF present; a signed token without one would never expire.
        # Every token finly mints (create_access_token, create_refresh_token) carries all three.
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            leeway=JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "sub", "jti"]},
        )
    except jwt.PyJWTError:  # F61 — expired, not yet valid, bad signature, malformed
        raise ValueError("Invalid token")
