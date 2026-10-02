import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


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
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.PyJWTError:  # F61 — was jose.JWTError (expired, bad signature, malformed)
        raise ValueError("Invalid token")
