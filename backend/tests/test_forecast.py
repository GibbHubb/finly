"""Tests for GET /api/v1/transactions/forecast"""
from datetime import date


def _auth_headers(client):
    client.post("/api/v1/auth/register", json={
        "email": "fc@finly.dev", "password": "pass123", "full_name": "FC User"
    })
    res = client.post("/api/v1/auth/login", data={"username": "fc@finly.dev", "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _add_tx(client, headers, amount, day, month=3, year=2026, category="food", tx_type="expense"):
    client.post("/api/v1/transactions/", json={
        "amount": str(amount),
        "type": tx_type,
        "category": category,
        "description": f"tx {day}",
        "transaction_date": f"{year}-{month:02d}-{day:02d}",
    }, headers=headers)


def test_forecast_insufficient_data(client):
    """Fewer than 5 data points → null projection with reason."""
    headers = _auth_headers(client)
    _add_tx(client, headers, 50.0, 1)
    _add_tx(client, headers, 30.0, 2)

    res = client.get("/api/v1/transactions/forecast", params={"month": 3, "year": 2026}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["projected_total"] is None
    assert body["reason"] == "insufficient_data"
    assert body["data_points_used"] == 2


def test_forecast_with_enough_data(client):
    """15 days of spend → returns a numeric projection."""
    headers = _auth_headers(client)
    for day in range(1, 16):
        _add_tx(client, headers, 20.0 + day, day)

    res = client.get("/api/v1/transactions/forecast", params={"month": 3, "year": 2026}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["projected_total"] is not None
    projected = float(body["projected_total"])
    # 15 days × ~28 avg = ~420; projection to day 31 should be > actual spend to date
    actual_to_date = sum(20.0 + d for d in range(1, 16))
    assert projected >= actual_to_date
    assert body["data_points_used"] == 15
    assert body["confidence"] in ("low", "medium", "high")


def test_forecast_no_transactions(client):
    """No transactions at all → null projection."""
    headers = _auth_headers(client)
    res = client.get("/api/v1/transactions/forecast", params={"month": 3, "year": 2026}, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["projected_total"] is None
    assert body["data_points_used"] == 0


def test_forecast_income_excluded(client):
    """Income transactions must not affect expense forecast."""
    headers = _auth_headers(client)
    # 5 income transactions
    for day in range(1, 6):
        _add_tx(client, headers, 1000.0, day, tx_type="income", category="salary")

    res = client.get("/api/v1/transactions/forecast", params={"month": 3, "year": 2026}, headers=headers)
    body = res.json()
    # Still insufficient data for expense forecast
    assert body["projected_total"] is None
