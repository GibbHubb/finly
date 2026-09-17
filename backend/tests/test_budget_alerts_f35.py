"""F35/F53 — a write that pushes a category over its budget returns the alert; nothing else does.

"Pushed over" = spend was <= limit before the write and > limit after it. An expense added to a
category that was ALREADY over does not alert (that would be news about the past), and edits and
splits alert exactly like creates (F53: they used to never alert).
"""
import pytest


def _h(client, email="f35@finly.dev"):
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass12345", "full_name": "F35"})
    r = client.post("/api/v1/auth/login", data={"username": email, "password": "pass12345"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _budget(client, h, category="food", limit="100.00"):
    r = client.post("/api/v1/budgets/", headers=h, json={"category": category, "limit_amount": limit, "month": 3, "year": 2026})
    assert r.status_code == 201, r.text


def _add(client, h, amount, category="food", day="2026-03-05"):
    r = client.post("/api/v1/transactions/", headers=h, json={
        "amount": amount, "type": "expense", "category": category, "description": "x",
        "transaction_date": day, "currency": "EUR"})
    assert r.status_code == 201, r.text
    return r.json()


def test_the_expense_that_crosses_the_limit_alerts(client, db):
    h = _h(client); _budget(client, h)
    first = _add(client, h, "60.00")
    assert first["budget_alerts"] == []  # 60 of 100
    second = _add(client, h, "50.00")    # 110 of 100: crossed
    [alert] = second["budget_alerts"]
    assert (alert["category"], alert["spent"], alert["limit"], alert["overage"]) == ("food", "110.00", "100.00", "10.00")


def test_an_expense_while_already_over_does_not_alert_again(client, db):
    h = _h(client); _budget(client, h)
    _add(client, h, "120.00")
    assert _add(client, h, "5.00")["budget_alerts"] == []


def test_no_budget_means_no_alert(client, db):
    h = _h(client)
    assert _add(client, h, "999.00")["budget_alerts"] == []


def test_a_patch_that_raises_the_amount_over_the_limit_alerts(client, db):  # F53
    h = _h(client); _budget(client, h)
    tx = _add(client, h, "40.00")
    r = client.patch(f"/api/v1/transactions/{tx['id']}", headers=h, json={"amount": "140.00"})
    assert r.status_code == 200
    assert [a["category"] for a in r.json()["budget_alerts"]] == ["food"]


def test_a_patch_that_moves_an_expense_into_a_budgeted_category_alerts_there(client, db):  # F53
    h = _h(client); _budget(client, h, category="transport", limit="50.00")
    tx = _add(client, h, "80.00", category="food")
    r = client.patch(f"/api/v1/transactions/{tx['id']}", headers=h, json={"category": "transport"})
    assert [a["category"] for a in r.json()["budget_alerts"]] == ["transport"]


def test_a_split_that_puts_part_of_an_expense_over_another_budget_alerts(client, db):  # F53
    h = _h(client); _budget(client, h, category="entertainment", limit="30.00")
    tx = _add(client, h, "100.00", category="food")
    r = client.post(f"/api/v1/transactions/{tx['id']}/split", headers=h, json={"children": [
        {"amount": "60.00", "category": "food"}, {"amount": "40.00", "category": "entertainment"}]})
    assert r.status_code == 200, r.text
    assert [a["category"] for a in r.json()["budget_alerts"]] == ["entertainment"]


def test_lists_carry_no_alerts(client, db):
    h = _h(client); _budget(client, h)
    _add(client, h, "150.00")
    assert all(t["budget_alerts"] == [] for t in client.get("/api/v1/transactions/", headers=h).json())
