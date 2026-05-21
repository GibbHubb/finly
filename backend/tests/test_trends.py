from datetime import date
from dateutil.relativedelta import relativedelta


def _auth_headers(client):
    client.post("/api/v1/auth/register", json={
        "email": "trends@finly.dev", "password": "pass123", "full_name": "Trends User",
    })
    res = client.post("/api/v1/auth/login", data={"username": "trends@finly.dev", "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _post_tx(client, headers, amount, tx_type, category, day):
    return client.post("/api/v1/transactions/", json={
        "amount": amount,
        "type": tx_type,
        "category": category,
        "description": "",
        "transaction_date": str(day),
    }, headers=headers)


def _first_of(delta_months: int) -> date:
    today = date.today()
    return (today.replace(day=1) - relativedelta(months=delta_months))


def test_trends_requires_auth(client):
    res = client.get("/api/v1/transactions/trends")
    assert res.status_code == 401


def test_trends_default_returns_six_months(client):
    headers = _auth_headers(client)
    res = client.get("/api/v1/transactions/trends", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 6
    # Oldest first, newest last
    assert data[0]["month"] < data[-1]["month"]
    # Empty user → every month has empty categories
    for entry in data:
        assert entry["categories"] == {}


def test_trends_aggregates_expense_by_category(client):
    headers = _auth_headers(client)
    today = date.today().replace(day=15)
    last_month = (today.replace(day=1) - relativedelta(months=1)).replace(day=15)

    _post_tx(client, headers, "120.00", "expense", "food", today)
    _post_tx(client, headers, "30.00", "expense", "food", today)
    _post_tx(client, headers, "600.00", "expense", "housing", today)
    _post_tx(client, headers, "400.00", "expense", "housing", last_month)
    # Income should be ignored by trends
    _post_tx(client, headers, "2500.00", "income", "salary", today)

    res = client.get("/api/v1/transactions/trends?months=3", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3

    current_key = today.strftime("%Y-%m")
    last_key = last_month.strftime("%Y-%m")
    by_month = {entry["month"]: entry["categories"] for entry in data}

    assert by_month[current_key]["food"] == "150.00"
    assert by_month[current_key]["housing"] == "600.00"
    assert by_month[last_key]["housing"] == "400.00"
    assert "salary" not in by_month[current_key]


def test_trends_zero_fills_empty_months(client):
    headers = _auth_headers(client)
    # Only a transaction two months ago — the month in between must still be present
    three_months_ago = _first_of(2)
    _post_tx(client, headers, "100.00", "expense", "food", three_months_ago.replace(day=10))

    res = client.get("/api/v1/transactions/trends?months=3", headers=headers)
    data = res.json()
    assert len(data) == 3
    # All month keys sorted ascending, no gaps
    keys = [e["month"] for e in data]
    assert keys == sorted(keys)


def test_trends_rejects_bad_window(client):
    headers = _auth_headers(client)
    res = client.get("/api/v1/transactions/trends?months=0", headers=headers)
    assert res.status_code == 422
    res = client.get("/api/v1/transactions/trends?months=25", headers=headers)
    assert res.status_code == 422
