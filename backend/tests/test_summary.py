def _auth_headers(client):
    client.post("/api/v1/auth/register", json={
        "email": "summary@finly.dev", "password": "pass123", "full_name": "Summary User"
    })
    res = client.post("/api/v1/auth/login", data={"username": "summary@finly.dev", "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _post_tx(client, headers, amount, tx_type, category, day="2024-06-15"):
    return client.post("/api/v1/transactions/", json={
        "amount": amount,
        "type": tx_type,
        "category": category,
        "description": "",
        "transaction_date": day,
    }, headers=headers)


def test_summary_empty_month(client):
    headers = _auth_headers(client)
    res = client.get("/api/v1/transactions/summary?month=6&year=2024", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_income"] == "0"
    assert data["total_expenses"] == "0"
    assert data["net"] == "0"
    assert data["categories"] == []


def test_summary_totals(client):
    headers = _auth_headers(client)
    _post_tx(client, headers, "1000.00", "income", "salary")
    _post_tx(client, headers, "200.00", "expense", "food")
    _post_tx(client, headers, "50.00", "expense", "food")

    res = client.get("/api/v1/transactions/summary?month=6&year=2024", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_income"] == "1000.00"
    assert data["total_expenses"] == "250.00"
    assert data["net"] == "750.00"

    categories = {c["category"]: c for c in data["categories"]}
    assert categories["food"]["expenses"] == "250.00"
    assert categories["salary"]["income"] == "1000.00"


def test_summary_with_budget(client):
    headers = _auth_headers(client)
    _post_tx(client, headers, "180.00", "expense", "food")

    # Set a budget for food in June 2024
    client.post("/api/v1/budgets/", json={
        "category": "food", "limit_amount": "300.00", "month": 6, "year": 2024
    }, headers=headers)

    res = client.get("/api/v1/transactions/summary?month=6&year=2024", headers=headers)
    data = res.json()
    food = next(c for c in data["categories"] if c["category"] == "food")
    assert food["budget_limit"] == "300.00"
    assert food["budget_remaining"] == "120.00"


def test_summary_excludes_other_months(client):
    headers = _auth_headers(client)
    _post_tx(client, headers, "500.00", "income", "salary", day="2024-05-10")

    res = client.get("/api/v1/transactions/summary?month=6&year=2024", headers=headers)
    data = res.json()
    assert data["total_income"] == "0"


def test_summary_requires_auth(client):
    res = client.get("/api/v1/transactions/summary?month=6&year=2024")
    assert res.status_code == 401
