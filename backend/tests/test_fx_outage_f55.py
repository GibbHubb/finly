"""F55 — an FX outage must REFUSE a change that needs a rate, and change nothing.

Since F52 a failed rate lookup yields None instead of a fake 1:1. Two writers stored that None
over correct data:
  * a base-currency change committed the new currency, THEN recomputed every row — during an
    outage it NULLed every converted `base_amount` (unrecoverable), returned 200, and a retry
    was impossible because re-selecting the now-saved currency is a no-op;
  * `update_transaction` re-priced an edited row to NULL the same way.

Owner decision (Max, 2026-09-16): when rates are unavailable, refuse and change nothing.

The rate fetch is driven through `httpx.MockTransport` on the service's real client (the F52
pattern), so the conversion code under test is the shipped one. Every "unchanged" assertion
reads back through a FRESH session, not the request's session, so it sees what was committed.
"""
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

from app.models.fx_rate import FxRate
from app.models.transaction import Transaction
from app.models.user import User
from app.services import rates_service

RATES = {"USD": 1.10, "GBP": 0.85, "SEK": 11.5, "NOK": 11.3, "DKK": 7.45}


@pytest.fixture
def fx(monkeypatch):
    """A switchable Frankfurter: mode 'ok' serves RATES, 'down' answers 503, 'no_gbp' serves
    every rate except GBP (a partial outage). `calls` counts requests that reached it."""
    state = {"mode": "ok", "calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["mode"] == "down":
            return httpx.Response(503, text="upstream down")
        rates = dict(RATES)
        if state["mode"] == "no_gbp":
            rates.pop("GBP")
        return httpx.Response(200, json={"amount": 1.0, "base": "EUR", "rates": rates})

    rates_service._CACHE.clear()
    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    yield state
    rates_service._CACHE.clear()


def _auth_headers(client, email="f55@finly.dev"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "pass12345", "full_name": "FX Outage",
    })
    res = client.post("/api/v1/auth/login", data={"username": email, "password": "pass12345"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _add(client, headers, amount, currency, day="2026-03-05"):
    res = client.post("/api/v1/transactions/", headers=headers, json={
        "amount": amount, "type": "expense", "category": "food",
        "description": f"{currency} row", "transaction_date": day, "currency": currency,
    })
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _start_outage(db, fx, mode="down"):
    """Forget every cached rate, then take the provider down. Without clearing `fx_rates` the
    DB cache would answer and no outage would ever be exercised."""
    db.query(FxRate).delete()
    db.commit()
    fx["mode"] = mode
    fx["calls"] = 0


def _committed(db):
    """(base_currency, full_name, {tx_id: (amount, currency, base_amount)}) as COMMITTED."""
    fresh = sessionmaker(bind=db.get_bind())()
    try:
        user = fresh.query(User).filter(User.email == "f55@finly.dev").one()
        rows = {t.id: (t.amount, t.currency, t.base_amount)
                for t in fresh.query(Transaction).filter(Transaction.user_id == user.id)}
        return user.base_currency, user.full_name, rows
    finally:
        fresh.close()


@pytest.fixture
def mixed(client, db, fx):
    """A EUR-based user holding one EUR, one USD and one GBP expense, each worth 100.00 EUR."""
    headers = _auth_headers(client)
    ids = {
        "EUR": _add(client, headers, "100.00", "EUR"),
        "USD": _add(client, headers, "110.00", "USD"),
        "GBP": _add(client, headers, "85.00", "GBP"),
    }
    cur, _, rows = _committed(db)
    assert cur == "EUR"
    assert [rows[ids[c]][2] for c in ("EUR", "USD", "GBP")] == [Decimal("100.00")] * 3
    return headers, ids


# ── base-currency change ───────────────────────────────────────────────────────
def test_base_currency_change_is_refused_during_an_outage_and_nothing_changes(client, db, fx, mixed):
    headers, ids = mixed
    before = _committed(db)
    _start_outage(db, fx)

    res = client.patch("/api/v1/auth/me", headers=headers,
                       json={"base_currency": "USD", "full_name": "Renamed"})

    assert res.status_code == 503
    assert "base currency was not changed" in res.json()["detail"]
    assert fx["calls"] > 0, "the outage was never reached — this test proves nothing"
    # The whole request is refused: currency, name and every base_amount exactly as before.
    assert _committed(db) == before
    assert client.get("/api/v1/auth/me", headers=headers).json()["base_currency"] == "EUR"


def test_a_refused_change_can_be_retried_once_rates_are_back(client, db, fx, mixed):
    """The old bug's second half: the currency was saved despite the failure, so selecting it
    again was a no-op and the NULLs could never be repaired."""
    headers, ids = mixed
    _start_outage(db, fx)
    assert client.patch("/api/v1/auth/me", headers=headers, json={"base_currency": "USD"}).status_code == 503

    fx["mode"] = "ok"
    res = client.patch("/api/v1/auth/me", headers=headers, json={"base_currency": "USD"})
    assert res.status_code == 200
    cur, _, rows = _committed(db)
    assert cur == "USD"
    assert all(r[2] == Decimal("110.00") for r in rows.values())


def test_a_partial_outage_still_refuses_and_writes_no_row(client, db, fx, mixed):
    """USD rates arrive, GBP's do not. The EUR row converts fine in memory — it must still not
    be written, or the ledger ends up half in USD and half in EUR under a USD label."""
    headers, ids = mixed
    before = _committed(db)
    _start_outage(db, fx, mode="no_gbp")

    res = client.patch("/api/v1/auth/me", headers=headers, json={"base_currency": "USD"})

    assert res.status_code == 503
    assert _committed(db) == before


def test_base_currency_change_converts_every_row_when_rates_are_available(client, db, fx, mixed):
    headers, ids = mixed
    _start_outage(db, fx, mode="ok")  # clear the cache so the change really fetches

    res = client.patch("/api/v1/auth/me", headers=headers, json={"base_currency": "USD"})

    assert res.status_code == 200
    assert res.json()["base_currency"] == "USD"
    cur, _, rows = _committed(db)
    assert cur == "USD"
    # 100 EUR -> 110 USD; 110 USD stays; 85 GBP -> 100 EUR -> 110 USD.
    assert {c: rows[ids[c]][2] for c in ids} == {
        "EUR": Decimal("110.00"), "USD": Decimal("110.00"), "GBP": Decimal("110.00"),
    }


def test_rows_already_in_the_new_base_currency_need_no_rate(client, db, fx):
    headers = _auth_headers(client)
    a = _add(client, headers, "110.00", "USD")
    b = _add(client, headers, "42.50", "USD", day="2026-04-01")
    _start_outage(db, fx)

    res = client.patch("/api/v1/auth/me", headers=headers, json={"base_currency": "USD"})

    assert res.status_code == 200
    assert fx["calls"] == 0, "a same-currency row asked for a rate"
    cur, _, rows = _committed(db)
    assert cur == "USD"
    assert rows[a][2] == Decimal("110.00") and rows[b][2] == Decimal("42.50")


# ── single-row writes ──────────────────────────────────────────────────────────
def test_update_transaction_is_refused_during_an_outage_and_the_row_is_unchanged(client, db, fx, mixed):
    headers, ids = mixed
    before = _committed(db)
    _start_outage(db, fx)

    for patch in ({"amount": "220.00"}, {"transaction_date": "2026-05-01"}, {"currency": "GBP"}):
        res = client.patch(f"/api/v1/transactions/{ids['USD']}", headers=headers, json=patch)
        assert res.status_code == 503, patch
        assert "not saved" in res.json()["detail"]
        assert _committed(db) == before, patch


def test_update_transaction_in_the_base_currency_needs_no_rate(client, db, fx, mixed):
    headers, ids = mixed
    _start_outage(db, fx)

    res = client.patch(f"/api/v1/transactions/{ids['EUR']}", headers=headers, json={"amount": "12.34"})

    assert res.status_code == 200
    assert fx["calls"] == 0
    assert _committed(db)[2][ids["EUR"]] == (Decimal("12.34"), "EUR", Decimal("12.34"))


def test_update_transaction_currency_change_reprices_the_row(client, db, fx, mixed):
    """Changing only the currency used to leave base_amount in the old currency's terms."""
    headers, ids = mixed
    res = client.patch(f"/api/v1/transactions/{ids['EUR']}", headers=headers, json={"currency": "usd"})
    assert res.status_code == 200
    assert _committed(db)[2][ids["EUR"]] == (Decimal("100.00"), "USD", Decimal("90.91"))


def test_update_transaction_rejects_an_unsupported_currency(client, db, fx, mixed):
    headers, ids = mixed
    res = client.patch(f"/api/v1/transactions/{ids['EUR']}", headers=headers, json={"currency": "XYZ"})
    assert res.status_code == 422


def test_create_is_refused_during_an_outage_unless_no_rate_is_needed(client, db, fx):
    headers = _auth_headers(client)
    _start_outage(db, fx)

    res = client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "110.00", "type": "expense", "category": "food",
        "description": "usd", "transaction_date": "2026-03-05", "currency": "USD",
    })
    assert res.status_code == 503
    assert _committed(db)[2] == {}, "a refused create still wrote a row"

    _add(client, headers, "10.00", "EUR")
    assert list(_committed(db)[2].values()) == [(Decimal("10.00"), "EUR", Decimal("10.00"))]


def test_split_is_refused_during_an_outage_and_adds_no_children(client, db, fx, mixed):
    headers, ids = mixed
    before = _committed(db)
    _start_outage(db, fx)

    res = client.post(f"/api/v1/transactions/{ids['USD']}/split", headers=headers, json={
        "children": [{"amount": "60.00", "category": "food"}, {"amount": "50.00", "category": "other"}],
    })

    assert res.status_code == 503
    assert _committed(db) == before
