"""F47 — the GoCardless client, the bank endpoints and the sync's status transitions.

The HTTP boundary (`httpx`) is mocked, never the service under test: the client's request
building, token caching and error mapping all run for real. The status machine follows
models/bank_connection.py: pending -> active on callback; active -> expired on 401/403 or a
requisition with no accounts; active -> error on anything else.
"""
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.models.bank_connection import BankConnection
from app.models.transaction import Transaction
from app.services import bank_sync_service
from app.services import gocardless_service as gc


class FakeHttp:
    """Answers GoCardless calls by (method, path suffix); records every call."""

    def __init__(self):
        self.routes: dict[tuple[str, str], tuple[int, object]] = {
            ("POST", "/token/new/"): (200, {"access": "tok-1"}),
        }
        self.calls: list[tuple[str, str, dict]] = []

    def _answer(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, suffix), (status, body) in self.routes.items():
            if m == method and url.endswith(suffix):
                if body is None:
                    return httpx.Response(status, request=httpx.Request(method, url))
                return httpx.Response(status, json=body, request=httpx.Request(method, url))
        raise AssertionError(f"unexpected {method} {url}")

    def post(self, url, **kw):
        return self._answer("POST", url, **kw)

    def request(self, method, url, **kw):
        return self._answer(method, url, **kw)


@pytest.fixture
def http(monkeypatch):
    fake = FakeHttp()
    monkeypatch.setattr(gc.httpx, "post", fake.post)
    monkeypatch.setattr(gc.httpx, "request", fake.request)
    monkeypatch.setattr(gc, "_token_cache", None)
    monkeypatch.setattr(gc.settings, "GOCARDLESS_SECRET_ID", "id")
    monkeypatch.setattr(gc.settings, "GOCARDLESS_SECRET_KEY", "key")
    return fake


def _headers(client, email="bank@finly.dev"):
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass12345", "full_name": "B"})
    tok = client.post("/api/v1/auth/login", data={"username": email, "password": "pass12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _booked(*rows):
    return {"transactions": {"booked": list(rows), "pending": []}}


def _row(amount, on, text, currency="EUR"):
    return {"transactionAmount": {"amount": amount, "currency": currency}, "bookingDate": on,
            "remittanceInformationUnstructured": text}


# --- gocardless_service ---------------------------------------------------------------------

def test_missing_credentials_is_a_503_error(monkeypatch):
    monkeypatch.setattr(gc, "_token_cache", None)
    monkeypatch.setattr(gc.settings, "GOCARDLESS_SECRET_ID", "")
    with pytest.raises(gc.GoCardlessError) as exc:
        gc.list_institutions()
    assert exc.value.status == 503


def test_token_is_minted_once_and_sent_as_bearer(http):
    http.routes[("GET", "/institutions/")] = (200, [{"id": "BANK_NL"}])
    assert gc.list_institutions("NL") == [{"id": "BANK_NL"}]
    assert gc.list_institutions("NL") == [{"id": "BANK_NL"}]
    posts = [c for c in http.calls if c[0] == "POST"]
    assert len(posts) == 1 and posts[0][2]["json"] == {"secret_id": "id", "secret_key": "key"}
    get = http.calls[-1]
    assert get[2]["headers"]["Authorization"] == "Bearer tok-1"
    assert get[2]["params"] == {"country": "NL"}


def test_token_failures_raise_with_the_status(http):
    http.routes[("POST", "/token/new/")] = (401, {"detail": "bad secret"})
    with pytest.raises(gc.GoCardlessError) as exc:
        gc.get_requisition("r1")
    assert exc.value.status == 401

    http.routes[("POST", "/token/new/")] = (200, {"nope": True})
    with pytest.raises(gc.GoCardlessError, match="no access token"):
        gc.get_requisition("r1")


def test_non_2xx_maps_to_an_error_and_empty_body_to_a_dict(http):
    http.routes[("GET", "/accounts/acc-1/transactions/")] = (403, {"summary": "consent expired"})
    with pytest.raises(gc.GoCardlessError) as exc:
        gc.fetch_transactions("acc-1")
    assert exc.value.status == 403 and "consent expired" in str(exc.value)

    http.routes[("GET", "/requisitions/r9/")] = (204, None)
    assert gc.get_requisition("r9") == {}


def test_create_requisition_sends_the_consent_body(http):
    http.routes[("POST", "/requisitions/")] = (201, {"id": "req-1", "link": "https://consent"})
    assert gc.create_requisition("INST")["id"] == "req-1"
    body = http.calls[-1][2]["json"]
    assert body["institution_id"] == "INST" and body["redirect"] == gc.settings.GOCARDLESS_REDIRECT_URL


# --- endpoints + status transitions ---------------------------------------------------------

def test_connect_callback_sync_status_happy_path(client, db, http):
    h = _headers(client)
    http.routes[("POST", "/requisitions/")] = (201, {"id": "req-1", "link": "https://consent/req-1"})
    res = client.post("/api/v1/bank/connect", headers=h).json()
    assert res["requisition_id"] == "req-1" and res["link"] == "https://consent/req-1"
    assert client.get("/api/v1/bank/status", headers=h).json()[0]["status"] == "pending"

    http.routes[("GET", "/requisitions/req-1/")] = (200, {"accounts": ["acc-1"], "institution_id": "ING_NL"})
    cb = client.get("/api/v1/bank/callback?ref=req-1", headers=h).json()
    assert cb == {"ok": True, "connection_id": res["connection_id"], "account_id": "acc-1"}

    http.routes[("GET", "/accounts/acc-1/transactions/")] = (200, _booked(
        _row("-12.50", "2026-03-02", "Albert Heijn"),
        _row("2500.00", "2026-03-25", "Salary"),
        _row("-12.50", "2026-03-02", "Albert Heijn"),   # same payment twice in one feed
        {"transactionAmount": {"amount": None}},         # skipped: no amount
        _row("abc", "2026-03-03", "garbage"),            # skipped: unparseable
        {"transactionAmount": {"amount": "-1"}},         # skipped: no date
        _row("-3", "not-a-date", "bad date"),            # skipped: bad date
    ))
    sync = client.post("/api/v1/bank/sync", headers=h).json()
    assert sync["results"][0]["inserted"] == 2 and sync["results"][0]["skipped"] == 1

    rows = {(t.description, t.type, t.amount, t.base_amount) for t in db.query(Transaction).all()}
    assert rows == {
        ("Albert Heijn", "expense", Decimal("12.50"), Decimal("12.50")),
        ("Salary", "income", Decimal("2500.00"), Decimal("2500.00")),
    }

    # A second sync of the same feed inserts nothing.
    again = client.post("/api/v1/bank/sync", headers=h).json()["results"][0]
    assert again["inserted"] == 0 and again["skipped"] == 3

    status = client.get("/api/v1/bank/status", headers=h).json()[0]
    assert status["institution_name"] == "ING_NL"
    assert status["status"] == "active" and status["needs_reconnect"] is False and status["last_sync_at"]


def test_connect_and_callback_surface_gocardless_errors(client, http):
    h = _headers(client)
    http.routes[("POST", "/requisitions/")] = (400, {"summary": "unknown institution"})
    res = client.post("/api/v1/bank/connect?institution_id=NOPE", headers=h)
    assert res.status_code == 400 and "unknown institution" in res.json()["detail"]

    assert client.get("/api/v1/bank/callback?ref=x", headers=h).status_code == 404

    http.routes[("POST", "/requisitions/")] = (201, {"id": "req-2", "link": "l"})
    client.post("/api/v1/bank/connect", headers=h)
    http.routes[("GET", "/requisitions/req-2/")] = (500, {"summary": "down"})
    assert client.get("/api/v1/bank/callback?ref=req-2", headers=h).status_code == 500


@pytest.fixture
def conn(db, client):
    _headers(client, "conn@finly.dev")
    from app.models.user import User
    uid = db.query(User).filter(User.email == "conn@finly.dev").one().id
    c = BankConnection(user_id=uid, requisition_id="req-x", institution_id="I", status="active", account_id="acc-x")
    db.add(c)
    db.commit()
    return c


@pytest.mark.parametrize("status,expected", [(401, "expired"), (403, "expired"), (500, "error"), (429, "error")])
def test_sync_failure_status_transitions(db, conn, http, status, expected):
    http.routes[("GET", "/accounts/acc-x/transactions/")] = (status, {"summary": "nope"})
    r = bank_sync_service.sync_connection(conn, db)
    assert conn.status == expected and r["inserted"] == 0 and r["error"] == conn.last_error


def test_a_requisition_without_accounts_is_expired(db, conn, http):
    conn.account_id = None
    http.routes[("GET", "/requisitions/req-x/")] = (200, {"accounts": []})
    r = bank_sync_service.sync_connection(conn, db)
    assert conn.status == "expired" and "reconnect" in r["error"]


def test_sync_all_active_skips_expired_and_counts(db, conn, http, monkeypatch):
    expired = BankConnection(user_id=conn.user_id, requisition_id="req-old", institution_id="I", status="expired")
    db.add(expired)
    db.commit()
    http.routes[("GET", "/accounts/acc-x/transactions/")] = (200, _booked(_row("-5", "2026-01-02", "Coffee")))
    res = bank_sync_service.sync_all_active(db)
    assert res == {"connections": 1, "inserted": 1, "skipped": 0, "errors": 0}
    assert db.query(Transaction).one().transaction_date == date(2026, 1, 2)


def test_sync_endpoint_reports_a_raised_gocardless_error(client, db, http, monkeypatch):
    h = _headers(client, "raise@finly.dev")
    http.routes[("POST", "/requisitions/")] = (201, {"id": "req-r", "link": "l"})
    client.post("/api/v1/bank/connect", headers=h)

    def boom(c, db):
        raise gc.GoCardlessError("token/new failed: 500", status=500)

    monkeypatch.setattr("app.api.v1.endpoints.bank.sync_connection", boom)
    res = client.post("/api/v1/bank/sync", headers=h).json()
    assert res["connections"] == 1
    assert res["results"][0]["error"] == "token/new failed: 500" and res["results"][0]["inserted"] == 0
