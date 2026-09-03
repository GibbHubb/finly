"""F48 — /health must never hand exception text to an anonymous caller.

`/health` is unauthenticated and publicly routed (vercel.json:22). It used to
return `str(exc)[:200]` on failure.

Measured 2026-09-03 against a deliberately fake DSN, this is what those 200
characters actually contained:

    (psycopg2.OperationalError) could not translate host name
    "db.abcdefgh.supabase.co" to address: Name or service not known

— the database host, i.e. the Supabase project ref, to anyone who curls it. The
USER shows up in the auth-failure shape ("password authentication failed for
user ..."); the PASSWORD does not appear in psycopg2 error text at all. So the
exposure is information disclosure, not credential disclosure — worth fixing,
worth stating accurately.

The endpoint must still be ABLE to report failure: F34 added it because a health
check that cannot fail tells you nothing (PT22 shipped a green check over a dead
database for days; RP15 the same). So these tests pin BOTH halves — it still
returns 503 on a real failure, and it returns an id instead of the detail.
"""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

# The shape of a real psycopg2 failure, with a canary host that must not escape.
CANARY_HOST = "db.f48canary.supabase.co"
CANARY_USER = "finly_canary_user"
REAL_ERROR_TEXT = (
    '(psycopg2.OperationalError) could not translate host name '
    f'"{CANARY_HOST}" to address: Name or service not known\n\n'
    'password authentication failed for user "%s"\n' % CANARY_USER
)


@pytest.fixture()
def db_down(monkeypatch):
    """Make the health check's engine.connect() fail the way production does."""
    def boom(*_a, **_kw):
        raise OperationalError(
            f"SELECT 1 -- {CANARY_HOST}", {}, Exception(REAL_ERROR_TEXT))

    import app.main as m
    monkeypatch.setattr(m.engine, "connect", boom)


def test_health_still_reports_failure(db_down):
    """The point of F34's health check: it has to be able to go red."""
    r = client.get("/health")
    assert r.status_code == 503, (
        "the health check stopped failing — a check that cannot fail is the "
        "PT22/RP15 defect, and worse than no check at all")
    assert r.json()["db"] == "down"


def test_health_does_not_leak_the_dsn(db_down):
    """The regression. Nothing from the connection string may reach the caller."""
    body = client.get("/health").text
    assert CANARY_HOST not in body, (
        "the database host (the Supabase project ref) was returned to an "
        "unauthenticated caller")
    assert CANARY_USER not in body, "the database user was returned"
    # Belt and braces: no DSN-shaped substring at all.
    assert not re.search(r"postgres(ql)?(\+\w+)?://", body), "a DSN reached the caller"
    assert "OperationalError" not in body, "raw exception class name returned"


def test_health_returns_a_correlatable_error_id(db_down):
    """Replacing the detail with nothing would also pass the test above, and
    would leave a 503 nobody can investigate. There has to be an id."""
    payload = client.get("/health").json()
    assert "error_id" in payload, "no error_id — the failure is unlookupable"
    assert re.fullmatch(r"[0-9a-f]{12}", payload["error_id"]), payload["error_id"]
    assert "error" not in payload, "the old free-text `error` field is still present"


def test_healthy_case_unchanged():
    """Positive control: the happy path must be untouched."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "up"}
