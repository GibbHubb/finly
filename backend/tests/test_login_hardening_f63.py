"""F63 — login hardening from the F60/F61 post-ship review.

(a) bcrypt runs with no transaction open, so neither the per-email advisory lock
    nor a pooled connection is held through it (the burst guarantee itself is
    the Postgres race test in test_login_lockout_race_f60.py).
(b) the lockout counter is keyed on the normalised email.
(c) decode_token requires exp, sub and jti.
"""
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

import app.services.auth as auth_module
from app.core import security
from app.core.config import settings
from app.core.security import hash_password
from app.models.login_attempt import LoginAttempt
from app.models.user import User

FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0)


def _add_user(db, email="bob@finly.dev", password="right-pass-1"):
    db.add(User(email=email, hashed_password=hash_password(password), full_name="b"))
    db.commit()


def _login(db, email, password):
    try:
        auth_module.login_user(email, password, db, now=FIXED_NOW)
    except HTTPException as e:
        return e.status_code
    return 200


# --- (a) the lock covers the reservation, not bcrypt -------------------------

@pytest.mark.parametrize("password", ["wrong", "right-pass-1"])
def test_bcrypt_runs_with_no_transaction_open(db, password):
    _add_user(db)
    seen = []
    real_verify = auth_module.verify_password

    def spy(plain, hashed):
        seen.append(db.in_transaction())
        return real_verify(plain, hashed)

    with mock.patch.object(auth_module, "verify_password", spy):
        _login(db, "bob@finly.dev", password)
    assert seen == [False], "bcrypt ran inside a transaction: the advisory lock and a pooled connection were held"


def test_the_attempt_is_reserved_before_bcrypt(db):
    """The row exists (committed) while bcrypt runs: that is what makes a
    concurrent sixth attempt count it."""
    _add_user(db)
    rows_during_bcrypt = []
    real_verify = auth_module.verify_password

    def spy(plain, hashed):
        rows_during_bcrypt.append(db.query(LoginAttempt).count())
        db.rollback()  # end the read transaction the spy itself opened
        return real_verify(plain, hashed)

    with mock.patch.object(auth_module, "verify_password", spy):
        _login(db, "bob@finly.dev", "wrong")
    assert rows_during_bcrypt == [1]


def test_a_successful_login_gives_its_reserved_slot_back(db):
    _add_user(db)
    assert [_login(db, "bob@finly.dev", "wrong") for _ in range(4)] == [401] * 4
    assert _login(db, "bob@finly.dev", "right-pass-1") == 200
    assert db.query(LoginAttempt).count() == 4  # the success left no row
    assert _login(db, "bob@finly.dev", "wrong") == 401  # 5th failure, not 429
    assert _login(db, "bob@finly.dev", "right-pass-1") == 429  # now locked, even with the right password


def test_unknown_email_still_counts_and_locks(db):
    assert [_login(db, "ghost@finly.dev", "x") for _ in range(6)] == [401] * 5 + [429]


# --- (b) the counter key is normalised ---------------------------------------

def test_lockout_key_normalises_case_and_whitespace():
    assert auth_module.lockout_key("  Bob@Finly.DEV ") == "bob@finly.dev"


def test_case_variants_share_one_lockout_counter(db):
    """Fails on the pre-F63 code: each casing had its own counter of 5."""
    _add_user(db)
    variants = ["Bob@finly.dev", "BOB@finly.dev", " bob@finly.dev", "bob@Finly.dev", "bOb@finly.dev"]
    assert [_login(db, v, "wrong") for v in variants] == [401] * 5
    assert _login(db, "bob@finly.dev", "wrong") == 429
    assert {r.email for r in db.query(LoginAttempt).all()} == {"bob@finly.dev"}


def test_account_lookup_stays_exact_match(db):
    """Decision (plan §5): only the COUNTER is normalised. Login itself still
    matches the email exactly as registered; changing that is an identity
    change with its own migration, not lockout hardening."""
    _add_user(db, email="Mixed@finly.dev")
    assert _login(db, "Mixed@finly.dev", "right-pass-1") == 200
    assert _login(db, "mixed@finly.dev", "right-pass-1") == 401


# --- (c) required claims ------------------------------------------------------

def _encode(**claims):
    now = datetime.now(timezone.utc)
    payload = {"sub": "1", "iat": now, "exp": now + timedelta(minutes=15), "jti": "j", "typ": "access"}
    payload.update(claims)
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@pytest.mark.parametrize("missing", ["exp", "sub", "jti"])
def test_a_token_missing_a_required_claim_is_rejected(missing):
    """Fails on the pre-F63 code for `exp`: a signed token without one decoded
    fine and never expired."""
    with pytest.raises(ValueError):
        security.decode_token(_encode(**{missing: None}))


@pytest.mark.parametrize("mint", [security.create_access_token, security.create_refresh_token])
def test_every_token_finly_mints_carries_the_required_claims(mint):
    payload = security.decode_token(mint(7, "some-jti"))
    assert {"exp", "sub", "jti"} <= payload.keys()


# --- review follow-up: an unknown email costs the same bcrypt as a wrong password ---

def test_unknown_email_still_runs_bcrypt(db):
    """Without this, an unknown email returns ~200 ms faster than a wrong password,
    which tells a caller which emails are registered."""
    with mock.patch.object(auth_module, "verify_password", wraps=auth_module.verify_password) as spy:
        assert _login(db, "nobody@finly.dev", "whatever-1") == 401
    assert spy.call_count == 1
