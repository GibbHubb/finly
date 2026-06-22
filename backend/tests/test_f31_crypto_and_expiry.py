"""F31 — Tests for Fernet crypto helper and bank-connection expiry logic.

Covers:
  1. encrypt/decrypt round-trip produces ciphertext != plaintext, and
     round-trips back to the original value.
  2. encrypt raises RuntimeError when FERNET_KEY is unset.
  3. sync_connection sets status="expired" on a mocked GoCardless 401.
  4. GET /bank/status returns needs_reconnect: true for an expired connection.
"""
from __future__ import annotations

import importlib
import unittest.mock as mock

import pytest
from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# 1 & 2 — Fernet crypto helper unit tests (no DB, no HTTP)
# ---------------------------------------------------------------------------

def _fresh_crypto_module(fernet_key: str):
    """Re-import crypto with settings.FERNET_KEY patched to *fernet_key*."""
    # We patch the settings object directly so the module picks up the override.
    import app.core.crypto as crypto_mod
    with mock.patch.object(
        crypto_mod.settings, "FERNET_KEY", fernet_key
    ):
        yield crypto_mod


@pytest.fixture()
def valid_key() -> str:
    return Fernet.generate_key().decode()


def test_encrypt_decrypt_roundtrip(valid_key):
    """Ciphertext != plaintext and round-trips back correctly."""
    import app.core.crypto as crypto_mod

    plaintext = "super-secret-token-abc123"
    with mock.patch.object(crypto_mod.settings, "FERNET_KEY", valid_key):
        ciphertext = crypto_mod.encrypt(plaintext)
        assert ciphertext != plaintext, "ciphertext must not equal plaintext"
        recovered = crypto_mod.decrypt(ciphertext)
        assert recovered == plaintext, "decrypt(encrypt(x)) must equal x"


def test_encrypt_raises_when_key_unset():
    """encrypt() must raise RuntimeError if FERNET_KEY is empty."""
    import app.core.crypto as crypto_mod

    with mock.patch.object(crypto_mod.settings, "FERNET_KEY", ""):
        with pytest.raises(RuntimeError, match="FERNET_KEY is not set"):
            crypto_mod.encrypt("anything")


def test_decrypt_raises_when_key_unset():
    """decrypt() must raise RuntimeError if FERNET_KEY is empty."""
    import app.core.crypto as crypto_mod

    with mock.patch.object(crypto_mod.settings, "FERNET_KEY", ""):
        with pytest.raises(RuntimeError, match="FERNET_KEY is not set"):
            crypto_mod.decrypt("gAAAAAB...")


# ---------------------------------------------------------------------------
# 3 — sync_connection sets status="expired" on a mocked GoCardless 401
# ---------------------------------------------------------------------------

def test_sync_connection_expired_on_401(db):
    """sync_connection flips status to 'expired' (not 'error') on a 401."""
    from app.models.bank_connection import BankConnection
    from app.services.bank_sync_service import sync_connection
    from app.services.gocardless_service import GoCardlessError

    # Insert a minimal connection row with a known account_id so we skip
    # the requisition-lookup branch and go straight to fetch_transactions.
    conn = BankConnection(
        user_id=1,
        requisition_id="req-test-401",
        account_id="acc-test-401",
        institution_id="TEST_INST",
        status="active",
    )
    db.add(conn)
    db.flush()

    with mock.patch(
        "app.services.bank_sync_service.gc.fetch_transactions",
        side_effect=GoCardlessError("Unauthorized", status=401),
    ):
        result = sync_connection(conn, db)

    assert conn.status == "expired", (
        f"Expected status='expired' on 401, got '{conn.status}'"
    )
    assert result["error"] is not None
    assert "401" in result["error"] or "expired" in result["error"].lower()


def test_sync_connection_error_on_transient(db):
    """sync_connection keeps status='error' for non-auth failures."""
    from app.models.bank_connection import BankConnection
    from app.services.bank_sync_service import sync_connection
    from app.services.gocardless_service import GoCardlessError

    conn = BankConnection(
        user_id=1,
        requisition_id="req-test-500",
        account_id="acc-test-500",
        institution_id="TEST_INST",
        status="active",
    )
    db.add(conn)
    db.flush()

    with mock.patch(
        "app.services.bank_sync_service.gc.fetch_transactions",
        side_effect=GoCardlessError("Internal Server Error", status=500),
    ):
        result = sync_connection(conn, db)

    assert conn.status == "error", (
        f"Expected status='error' on 500, got '{conn.status}'"
    )


# ---------------------------------------------------------------------------
# 4 — GET /bank/status returns needs_reconnect: true for an expired row
# ---------------------------------------------------------------------------

def _register_and_login(client) -> dict:
    client.post("/api/v1/auth/register", json={
        "email": "bank31@finly.dev",
        "password": "pass1234",
        "full_name": "Bank Tester",
    })
    res = client.post("/api/v1/auth/login", data={
        "username": "bank31@finly.dev",
        "password": "pass1234",
    })
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_bank_status_needs_reconnect(client, db):
    """GET /bank/status includes needs_reconnect=true for an expired connection."""
    from app.models.bank_connection import BankConnection
    from app.models.user import User

    headers = _register_and_login(client)

    # Locate the user we just created so we can attach a connection row.
    user = db.query(User).filter(User.email == "bank31@finly.dev").first()
    assert user is not None

    conn = BankConnection(
        user_id=user.id,
        requisition_id="req-expired-ui",
        institution_id="TEST_INST",
        status="expired",
        last_error="Auth failed (401) — consent has expired. Please reconnect.",
    )
    db.add(conn)
    db.commit()

    res = client.get("/api/v1/bank/status", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    row = data[0]
    assert row["status"] == "expired"
    assert row["needs_reconnect"] is True


def test_bank_status_active_no_reconnect(client, db):
    """GET /bank/status has needs_reconnect=false for an active connection."""
    from app.models.bank_connection import BankConnection
    from app.models.user import User

    # Register a separate user to avoid row collision with the other test.
    client.post("/api/v1/auth/register", json={
        "email": "bank31active@finly.dev",
        "password": "pass1234",
        "full_name": "Bank Active",
    })
    res = client.post("/api/v1/auth/login", data={
        "username": "bank31active@finly.dev",
        "password": "pass1234",
    })
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    user = db.query(User).filter(User.email == "bank31active@finly.dev").first()
    conn = BankConnection(
        user_id=user.id,
        requisition_id="req-active-ui",
        institution_id="TEST_INST",
        status="active",
    )
    db.add(conn)
    db.commit()

    res = client.get("/api/v1/bank/status", headers=headers)
    assert res.status_code == 200
    row = res.json()[0]
    assert row["status"] == "active"
    assert row["needs_reconnect"] is False
