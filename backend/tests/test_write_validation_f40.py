"""F40 — the API accepts on update exactly what it accepts on create.

Reproduced 2026-09-03 against the real schema: PATCH took a negative amount and an unknown
currency, a budget for "grocerys" was created and then matched no spend, and "" was a valid
password. (The currency-change re-pricing half of this plan shipped with F55; it is asserted
again here so the whole plan's criteria live in one file.)
"""
from decimal import Decimal

import httpx
import pytest

from app.models.fx_rate import FxRate
from app.services import rates_service
from app.models.transaction import Category


@pytest.fixture
def fx(monkeypatch):
    """1 EUR = 2 USD, as in the plan's reproduction."""
    def handler(request):
        return httpx.Response(200, json={"amount": 1.0, "base": "EUR", "rates": {"USD": 2.0, "GBP": 0.85,
                                                                            "SEK": 11.5, "NOK": 11.3, "DKK": 7.45}})
    rates_service._CACHE.clear()
    monkeypatch.setattr(rates_service, "_CLIENT", httpx.Client(transport=httpx.MockTransport(handler)))
    yield
    rates_service._CACHE.clear()


def _headers(client, email="f40@finly.dev"):
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass12345", "full_name": "F40"})
    res = client.post("/api/v1/auth/login", data={"username": email, "password": "pass12345"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _tx(client, headers, amount="100.00", currency="USD"):
    res = client.post("/api/v1/transactions/", headers=headers, json={
        "amount": amount, "type": "expense", "category": "food", "description": "x",
        "transaction_date": "2026-03-05", "currency": currency})
    assert res.status_code == 201, res.text
    return res.json()


# ── transactions ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("amount", [-500, 0])
def test_patch_refuses_a_non_positive_amount_and_changes_nothing(client, db, fx, amount):
    h = _headers(client)
    tx = _tx(client, h)

    res = client.patch(f"/api/v1/transactions/{tx['id']}", headers=h, json={"amount": amount})

    assert res.status_code == 422
    after = next(t for t in client.get("/api/v1/transactions/", headers=h).json() if t["id"] == tx["id"])
    assert Decimal(after["amount"]) == Decimal("100.00")


def test_patch_accepts_a_positive_amount(client, db, fx):  # control
    h = _headers(client)
    tx = _tx(client, h)
    res = client.patch(f"/api/v1/transactions/{tx['id']}", headers=h, json={"amount": "40.00"})
    assert res.status_code == 200 and Decimal(res.json()["amount"]) == Decimal("40.00")


def test_patch_currency_is_validated_and_normalised(client, db, fx):
    h = _headers(client)
    tx = _tx(client, h, currency="EUR")
    bad = client.patch(f"/api/v1/transactions/{tx['id']}", headers=h, json={"currency": "XYZ"})
    assert bad.status_code == 422 and "Unsupported currency" in bad.text
    ok = client.patch(f"/api/v1/transactions/{tx['id']}", headers=h, json={"currency": "usd"})
    assert ok.status_code == 200 and ok.json()["currency"] == "USD"


def test_patching_only_currency_reprices_the_row(client, db, fx):
    h = _headers(client)
    tx = _tx(client, h, amount="100.00", currency="USD")
    assert Decimal(tx["base_amount"]) == Decimal("50.00")

    res = client.patch(f"/api/v1/transactions/{tx['id']}", headers=h, json={"currency": "EUR"})

    assert res.status_code == 200 and Decimal(res.json()["base_amount"]) == Decimal("100.00")


def test_a_split_child_cannot_be_negative(client, db, fx):
    h = _headers(client)
    tx = _tx(client, h, amount="100.00", currency="EUR")
    res = client.post(f"/api/v1/transactions/{tx['id']}/split", headers=h, json={"children": [
        {"amount": "150.00", "category": "food"}, {"amount": "-50.00", "category": "other"}]})
    assert res.status_code == 422


# ── budgets ─────────────────────────────────────────────────────────────────
def _budget(client, h, **over):
    body = {"category": "food", "limit_amount": "300.00", "month": 6, "year": 2026, **over}
    return client.post("/api/v1/budgets/", headers=h, json=body)


def test_a_budget_for_an_unknown_category_is_refused(client, db):
    res = _budget(client, _headers(client), category="grocerys")
    assert res.status_code == 422 and "Unknown category" in res.text


def test_every_real_category_is_still_accepted(client, db):
    h = _headers(client)
    for i, c in enumerate(Category):
        res = _budget(client, h, category=c.value, month=(i % 12) + 1)
        assert res.status_code == 201, (c, res.text)
        assert res.json()["category"] == c.value


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_a_budget_limit_must_be_positive(client, db, limit):
    assert _budget(client, _headers(client), limit_amount=limit).status_code == 422


def test_a_budget_year_must_be_plausible(client, db):
    assert _budget(client, _headers(client), year=99999).status_code == 422


# ── auth ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("pw", ["", "abc", "1234567"])
def test_register_refuses_a_short_password(client, db, pw):
    res = client.post("/api/v1/auth/register", json={"email": "short@finly.dev", "password": pw, "full_name": "S"})
    assert res.status_code == 422


@pytest.mark.parametrize("pw", ["demo-only-not-a-secret", "e2e-pass-123", "12345678"])
def test_existing_demo_and_e2e_passwords_still_register(client, db, pw):
    res = client.post("/api/v1/auth/register", json={"email": f"{len(pw)}@finly.dev", "password": pw, "full_name": "S"})
    assert res.status_code == 201, res.text


def test_a_valid_split_is_accepted(client, db, fx):  # control: the 422 above is about the sign
    h = _headers(client)
    tx = _tx(client, h, amount="100.00", currency="EUR")
    res = client.post(f"/api/v1/transactions/{tx['id']}/split", headers=h, json={"children": [
        {"amount": "60.00", "category": "food"}, {"amount": "40.00", "category": "other"}]})
    assert res.status_code == 200, res.text


def test_a_password_change_has_the_same_floor(client, db):  # /code-review on F40
    h = _headers(client)
    bad = client.patch("/api/v1/auth/me", headers=h, json={"current_password": "pass12345", "new_password": ""})
    assert bad.status_code == 422
    ok = client.patch("/api/v1/auth/me", headers=h, json={"current_password": "pass12345", "new_password": "newpass123"})
    assert ok.status_code == 200, ok.text
