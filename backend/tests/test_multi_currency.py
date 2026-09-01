"""Tests for F12 — multi-currency (base_amount + recompute on base-currency change).

These tests stub out the Frankfurter HTTP call so they run offline and
deterministically: rates are seeded directly into `fx_rates`.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.fx_rate import FxRate
from app.services import rates_service


def _auth_headers(client, email="fx@finly.dev"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "pass123", "full_name": "FX User",
    })
    res = client.post("/api/v1/auth/login", data={"username": email, "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _stub_frankfurter(monkeypatch):
    """Replace the live Frankfurter fetch with a fixed EUR/USD/GBP rate table."""
    def fake(d: date) -> dict[str, Decimal]:
        return {
            "EUR": Decimal("1"),
            "USD": Decimal("1.10"),
            "GBP": Decimal("0.85"),
            "SEK": Decimal("11.5"),
            "NOK": Decimal("11.3"),
            "DKK": Decimal("7.45"),
        }
    monkeypatch.setattr(rates_service, "_fetch_historical_eur_rates", fake)


def test_base_amount_equals_amount_when_currency_matches_base(client):
    headers = _auth_headers(client)
    # default base_currency is EUR; transaction also EUR
    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "100.00", "type": "expense", "category": "food",
        "description": "euro shop", "transaction_date": "2026-03-05", "currency": "EUR",
    })
    txs = client.get("/api/v1/transactions/", headers=headers).json()
    # TransactionOut doesn't expose base_amount yet, but summary uses it.
    res = client.get("/api/v1/transactions/summary?month=3&year=2026", headers=headers)
    data = res.json()
    assert data["total_expenses"] == "100.00"


def test_base_amount_converted_when_currency_differs(client, db):
    headers = _auth_headers(client)
    # Add a USD transaction — user's base_currency is EUR (default).
    # Stubbed rate: 1 EUR = 1.10 USD, so 110 USD = 100 EUR.
    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "110.00", "type": "expense", "category": "shopping",
        "description": "usd shop", "transaction_date": "2026-03-15", "currency": "USD",
    })
    res = client.get("/api/v1/transactions/summary?month=3&year=2026", headers=headers)
    assert res.json()["total_expenses"] == "100.00"

    # The rate was cached in fx_rates
    assert db.query(FxRate).filter(FxRate.rate_date == date(2026, 3, 15)).count() >= 2


def test_changing_base_currency_recomputes_base_amount(client):
    headers = _auth_headers(client)
    # Log one EUR and one USD transaction at different dates
    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "100.00", "type": "expense", "category": "food",
        "description": "eur", "transaction_date": "2026-03-05", "currency": "EUR",
    })
    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "110.00", "type": "expense", "category": "food",
        "description": "usd", "transaction_date": "2026-03-10", "currency": "USD",
    })
    # Initial totals in EUR: 100 + 100 = 200
    assert client.get("/api/v1/transactions/summary?month=3&year=2026", headers=headers).json()["total_expenses"] == "200.00"

    # Change base to USD
    res = client.patch("/api/v1/auth/me", headers=headers, json={"base_currency": "USD"})
    assert res.status_code == 200
    assert res.json()["base_currency"] == "USD"

    # Expected totals in USD: 100 EUR -> 110 USD, 110 USD stays 110 USD  => 220
    assert client.get("/api/v1/transactions/summary?month=3&year=2026", headers=headers).json()["total_expenses"] == "220.00"


def test_unsupported_currency_rejected(client):
    headers = _auth_headers(client)
    res = client.patch("/api/v1/auth/me", headers=headers, json={"base_currency": "JPY"})
    assert res.status_code == 400


def test_userout_exposes_base_currency(client):
    headers = _auth_headers(client)
    res = client.get("/api/v1/auth/me", headers=headers)
    body = res.json()
    assert body["base_currency"] == "EUR"
