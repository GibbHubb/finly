import unittest.mock as mock
from datetime import datetime, timedelta

import pytest

from app.core.config import Settings
from app.core.security import create_access_token, create_refresh_token, decode_token


def test_register_and_login(client):
    # Register
    res = client.post("/api/v1/auth/register", json={
        "email": "test@finly.dev",
        "password": "SecurePass123",
        "full_name": "Test User",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "test@finly.dev"

    # Login
    res = client.post("/api/v1/auth/login", data={
        "username": "test@finly.dev",
        "password": "SecurePass123",
    })
    assert res.status_code == 200
    body = res.json()
    assert "access_token" in body
    assert "refresh_token" in body and body["refresh_token"]


def test_duplicate_email(client):
    payload = {"email": "dupe@finly.dev", "password": "pass12345", "full_name": "Dupe"}
    client.post("/api/v1/auth/register", json=payload)
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 400


def test_me_requires_auth(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# F42 — helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, email="f42@finly.dev", password="SecurePass123"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "full_name": "F42 Tester",
    })
    res = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200
    return res.json()


def _access_token_jti(access_token: str) -> str:
    return decode_token(access_token)["jti"]


# ---------------------------------------------------------------------------
# F42 — access + refresh claims
# ---------------------------------------------------------------------------

def test_access_token_carries_jti_and_typ(client):
    pair = _register_and_login(client, "claims@finly.dev")
    access_payload = decode_token(pair["access_token"])
    refresh_payload = decode_token(pair["refresh_token"])
    assert access_payload["typ"] == "access"
    assert refresh_payload["typ"] == "refresh"
    assert access_payload["jti"] == refresh_payload["jti"]


def test_refresh_token_cannot_be_used_as_access_token(client):
    pair = _register_and_login(client, "typeconfusion@finly.dev")
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['refresh_token']}"})
    assert res.status_code == 401


def test_me_rejects_a_malformed_token(client):
    res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt-at-all"})
    assert res.status_code == 401


def test_me_rejects_a_well_formed_token_with_no_matching_session(client, db):
    """A syntactically valid, correctly-signed access token whose `jti` has
    no row in refresh_tokens — e.g. forged, or from before this feature
    existed — must be rejected, not just an expired/revoked one."""
    from app.models.user import User

    _register_and_login(client, "nosession@finly.dev")
    user_id = db.query(User.id).filter(User.email == "nosession@finly.dev").scalar()
    orphan_token = create_access_token(user_id, "jti-with-no-db-row")

    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {orphan_token}"})
    assert res.status_code == 401


def test_refresh_rejects_an_access_token(client):
    """Type confusion the other way: an access token presented to /auth/refresh."""
    pair = _register_and_login(client, "refreshtypeconfusion@finly.dev")
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["access_token"]})
    assert res.status_code == 401


def test_refresh_rejects_a_malformed_token(client):
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage"})
    assert res.status_code == 401


def test_refresh_rejects_an_unknown_jti(client, db):
    """A well-formed, correctly-signed refresh token whose `jti` was never
    issued (forged) must be rejected."""
    from app.models.user import User

    _register_and_login(client, "forgedrefresh@finly.dev")
    user_id = db.query(User.id).filter(User.email == "forgedrefresh@finly.dev").scalar()
    forged = create_refresh_token(user_id, "jti-never-issued")

    res = client.post("/api/v1/auth/refresh", json={"refresh_token": forged})
    assert res.status_code == 401


def test_refresh_rejects_when_the_db_row_expiry_has_passed(client, db):
    """The stored `expires_at` is checked independently of the JWT's own
    `exp` — e.g. a session shortened administratively without reissuing the
    token must still be refused."""
    from app.models.refresh_token import RefreshToken

    pair = _register_and_login(client, "dbexpired@finly.dev")
    jti = _access_token_jti(pair["access_token"])
    row = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    row.expires_at = datetime(2020, 1, 1)
    db.commit()

    res = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# F42 — rotation + replay detection (§3 criterion 1)
# ---------------------------------------------------------------------------

def test_refresh_rotates_and_replay_is_rejected(client):
    pair = _register_and_login(client, "rotate@finly.dev")

    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r1.status_code == 200
    new_pair = r1.json()
    assert new_pair["refresh_token"] != pair["refresh_token"]
    assert new_pair["access_token"] != pair["access_token"]

    # The new access token works.
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_pair['access_token']}"})
    assert me.status_code == 200

    # Replaying the CONSUMED refresh token is rejected.
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert replay.status_code == 401


def test_refresh_replay_revokes_the_whole_chain(client):
    """Reuse of a consumed token is treated as a possible theft: every other
    active session for that user is revoked too, not just the replayed one."""
    pair = _register_and_login(client, "chain@finly.dev")
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]}).json()

    # Replay the old (already-consumed) token -> chain revoked.
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert replay.status_code == 401

    # The token issued BY the rotation is now also dead.
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    assert me.status_code == 401
    refresh_again = client.post("/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert refresh_again.status_code == 401


# ---------------------------------------------------------------------------
# F42 — logout revokes both halves (§3 criterion 2)
# ---------------------------------------------------------------------------

def test_logout_revokes_refresh_and_kills_the_access_token(client):
    pair = _register_and_login(client, "logout@finly.dev")

    # Access token works before logout.
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"}).status_code == 200

    out = client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]})
    assert out.status_code == 204

    # Refresh is dead.
    refresh_after = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refresh_after.status_code == 401

    # The STILL-UNEXPIRED access token is also dead (jti revoked).
    me_after = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert me_after.status_code == 401


def test_logout_is_idempotent(client):
    pair = _register_and_login(client, "logouttwice@finly.dev")
    assert client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}).status_code == 204
    # Logging out again with the same (already-revoked) token is not an error.
    assert client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]}).status_code == 204
    # Garbage input is not an error either.
    assert client.post("/api/v1/auth/logout", json={"refresh_token": "not-a-real-token"}).status_code == 204


# ---------------------------------------------------------------------------
# F42 — control: the revocation check is load-bearing (§9 "Control")
# ---------------------------------------------------------------------------

def test_control_revocation_check_is_load_bearing(client, db):
    """Prove the 401 after logout is gated on `revoked_at`, not some other
    coincidence: clear exactly that field back to NULL by hand and confirm
    the SAME access token starts working again (§9 Control)."""
    from app.models.refresh_token import RefreshToken

    pair = _register_and_login(client, "control-revoke@finly.dev")
    client.post("/api/v1/auth/logout", json={"refresh_token": pair["refresh_token"]})

    denied = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert denied.status_code == 401

    jti = _access_token_jti(pair["access_token"])
    row = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    row.revoked_at = None
    db.commit()

    allowed = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert allowed.status_code == 200, "control failed: clearing revoked_at should have let the token back in"


# ---------------------------------------------------------------------------
# F42 — SECRET_KEY fail-fast (§3 criterion 3)
# ---------------------------------------------------------------------------

def test_secret_key_default_raises_off_sqlite():
    with pytest.raises(Exception):
        Settings(_env_file=None, DATABASE_URL="postgresql://u:p@host:5432/db",
                 SECRET_KEY="dev-secret-change-in-prod")


def test_secret_key_unset_raises_off_sqlite():
    with pytest.raises(Exception):
        Settings(_env_file=None, DATABASE_URL="postgresql://u:p@host:5432/db", SECRET_KEY="")


def test_secret_key_default_is_fine_on_sqlite():
    s = Settings(_env_file=None, DATABASE_URL="sqlite:///./whatever.db",
                 SECRET_KEY="dev-secret-change-in-prod")
    assert s.SECRET_KEY == "dev-secret-change-in-prod"


def test_secret_key_real_value_boots_off_sqlite():
    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@host:5432/db",
                 SECRET_KEY="a-real-random-secret")
    assert s.SECRET_KEY == "a-real-random-secret"


# ---------------------------------------------------------------------------
# F42 — login lockout, fixed clock (§3 criterion 4)
# ---------------------------------------------------------------------------

def test_sixth_failed_login_is_429_with_fixed_clock(client):
    email = "lockout@finly.dev"
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "CorrectPass123", "full_name": "Lockout",
    })

    fixed_now = datetime(2026, 1, 1, 12, 0, 0)
    import app.services.auth as auth_module

    with mock.patch.object(auth_module, "datetime") as mock_dt:
        mock_dt.utcnow.return_value = fixed_now

        responses = []
        for _ in range(6):
            responses.append(client.post("/api/v1/auth/login", data={
                "username": email, "password": "WrongPassword",
            }))

    statuses = [r.status_code for r in responses]
    assert statuses[:5] == [401] * 5, statuses
    assert statuses[5] == 429, statuses


def test_correct_password_different_email_same_window_still_200(client):
    locked_email = "lockout-other@finly.dev"
    other_email = "not-locked-out@finly.dev"
    for email in (locked_email, other_email):
        client.post("/api/v1/auth/register", json={
            "email": email, "password": "CorrectPass123", "full_name": "T",
        })

    fixed_now = datetime(2026, 1, 1, 12, 0, 0)
    import app.services.auth as auth_module

    with mock.patch.object(auth_module, "datetime") as mock_dt:
        mock_dt.utcnow.return_value = fixed_now
        for _ in range(5):
            client.post("/api/v1/auth/login", data={"username": locked_email, "password": "wrong"})
        locked_out = client.post("/api/v1/auth/login", data={"username": locked_email, "password": "wrong"})
        other_ok = client.post("/api/v1/auth/login", data={"username": other_email, "password": "CorrectPass123"})

    assert locked_out.status_code == 429
    assert other_ok.status_code == 200


def test_lockout_window_expires(client):
    """Outside the 60s window, the counter resets — this is a lockout, not a ban."""
    email = "lockout-expires@finly.dev"
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "CorrectPass123", "full_name": "T",
    })

    import app.services.auth as auth_module
    t0 = datetime(2026, 1, 1, 12, 0, 0)

    with mock.patch.object(auth_module, "datetime") as mock_dt:
        mock_dt.utcnow.return_value = t0
        for _ in range(5):
            client.post("/api/v1/auth/login", data={"username": email, "password": "wrong"})

        # 61 seconds later: the window has rolled past all 5 failures.
        mock_dt.utcnow.return_value = t0 + timedelta(seconds=61)
        res = client.post("/api/v1/auth/login", data={"username": email, "password": "CorrectPass123"})

    assert res.status_code == 200


def test_control_lockout_threshold_is_load_bearing(client):
    """Raise the threshold absurdly high and confirm the 429 test goes red
    (§9 Control) — proves the earlier test exercises the real gate."""
    email = "lockout-control@finly.dev"
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "CorrectPass123", "full_name": "T",
    })

    import app.services.auth as auth_module
    fixed_now = datetime(2026, 1, 1, 12, 0, 0)

    with mock.patch.object(auth_module, "LOGIN_LOCKOUT_THRESHOLD", 1000), \
         mock.patch.object(auth_module, "datetime") as mock_dt:
        mock_dt.utcnow.return_value = fixed_now
        last = None
        for _ in range(6):
            last = client.post("/api/v1/auth/login", data={"username": email, "password": "wrong"})
    assert last.status_code == 401, "expected the 6th attempt to stay 401 with the gate effectively disabled"
