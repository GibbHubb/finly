"""F31 — Fernet symmetric-encryption helpers for at-rest secrets.

Usage
-----
    from app.core.crypto import encrypt, decrypt

    ciphertext = encrypt(plaintext_str)   # → URL-safe base64 token
    plaintext  = decrypt(ciphertext)      # → original string

Both functions raise ``RuntimeError`` immediately if ``settings.FERNET_KEY``
is unset or empty — they *never* silently return plaintext.  The app still
boots with an empty key (matching the F27 "empty creds = clean boot" pattern);
only code paths that actually call encrypt/decrypt will fail.

Key generation
--------------
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Store the result in the ``FERNET_KEY`` env var (never commit it).
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken  # noqa: F401 — re-export InvalidToken

from app.core.config import settings


def _get_fernet() -> Fernet:
    key = settings.FERNET_KEY
    if not key:
        raise RuntimeError(
            "FERNET_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\" "
            "and add it to your .env file."
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* and return a URL-safe base64 Fernet token (str)."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet *token* and return the original plaintext (str).

    Raises ``cryptography.fernet.InvalidToken`` if the token is tampered or
    was encrypted with a different key.
    """
    return _get_fernet().decrypt(token.encode()).decode()
