def _auth_headers(client):
    client.post("/api/v1/auth/register", json={
        "email": "budget@finly.dev", "password": "pass123", "full_name": "Budget User"
    })
    res = client.post("/api/v1/auth/login", data={"username": "budget@finly.dev", "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


BUDGET_PAYLOAD = {"category": "food", "limit_amount": "300.00", "month": 6, "year": 2024}


def test_create_and_list_budget(client):
    headers = _auth_headers(client)

    res = client.post("/api/v1/budgets/", json=BUDGET_PAYLOAD, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["category"] == "food"
    assert data["limit_amount"] == "300.00"

    res = client.get("/api/v1/budgets/", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_list_budgets_filter_by_month(client):
    headers = _auth_headers(client)
    client.post("/api/v1/budgets/", json=BUDGET_PAYLOAD, headers=headers)
    client.post("/api/v1/budgets/", json={**BUDGET_PAYLOAD, "month": 7}, headers=headers)

    res = client.get("/api/v1/budgets/?month=6&year=2024", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["month"] == 6


def test_duplicate_budget_rejected(client):
    headers = _auth_headers(client)
    client.post("/api/v1/budgets/", json=BUDGET_PAYLOAD, headers=headers)
    res = client.post("/api/v1/budgets/", json=BUDGET_PAYLOAD, headers=headers)
    assert res.status_code == 409


def test_delete_budget(client):
    headers = _auth_headers(client)
    res = client.post("/api/v1/budgets/", json=BUDGET_PAYLOAD, headers=headers)
    budget_id = res.json()["id"]

    res = client.delete(f"/api/v1/budgets/{budget_id}", headers=headers)
    assert res.status_code == 204

    res = client.get("/api/v1/budgets/", headers=headers)
    assert res.json() == []


def test_delete_budget_not_found(client):
    headers = _auth_headers(client)
    res = client.delete("/api/v1/budgets/9999", headers=headers)
    assert res.status_code == 404


def test_budget_requires_auth(client):
    res = client.get("/api/v1/budgets/")
    assert res.status_code == 401
