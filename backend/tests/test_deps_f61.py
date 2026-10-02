"""F61 — behaviour that the dependency swap (python-jose -> PyJWT, cryptography 43 -> 50) could change."""
from datetime import datetime, timedelta, timezone
from unittest import mock

import jwt
import pytest

from app.core import security
from app.core.config import settings


def _token_issued(ahead_seconds: int) -> str:
    """A token whose `iat` is in the future, as one minted by an instance with a fast clock."""
    now = datetime.now(timezone.utc) + timedelta(seconds=ahead_seconds)
    payload = {"sub": "1", "iat": now, "exp": now + timedelta(minutes=15), "jti": "j", "typ": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def test_a_token_from_a_clock_5s_ahead_is_accepted():
    assert security.decode_token(_token_issued(5))["sub"] == "1"


def test_a_token_from_a_clock_60s_ahead_is_still_rejected():
    with pytest.raises(ValueError, match="Invalid token"):
        security.decode_token(_token_issued(60))


def test_leeway_is_what_admits_the_5s_token():
    """Control: with no leeway the same 5s-ahead token fails, so the leeway is load-bearing."""
    with mock.patch.object(security, "JWT_LEEWAY_SECONDS", 0):
        with pytest.raises(ValueError):
            security.decode_token(_token_issued(5))


# Produced with cryptography==43.0.3 (the pin before F61) in a throwaway --target install:
#   Fernet(FERNET_KEY_43).encrypt(b"gocardless-refresh-token-f61")
FERNET_KEY_43 = "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXphYmNkZWY="
FERNET_TOKEN_43 = (
    "gAAAAABqv4qgsO5rkIP0c7BU9hpHOib7yjzBSKOn9gkA0T3B2to3Etpwh5zaM4JMc6zXZSir5Y_cghDCsOSAaFzF8xXP"
    "IZ8a9klNzp6E3zk5gNC3W7o0Zp4="
)


def test_ciphertext_written_by_cryptography_43_still_decrypts():
    import app.core.crypto as crypto_mod

    with mock.patch.object(crypto_mod.settings, "FERNET_KEY", FERNET_KEY_43):
        assert crypto_mod.decrypt(FERNET_TOKEN_43) == "gocardless-refresh-token-f61"
