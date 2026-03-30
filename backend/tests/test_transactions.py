def _auth_headers(client):
    client.post("/api/v1/auth/register", json={
        "email": "tx@finly.dev", "password": "pass123", "full_name": "Tx User"
    })
    res = client.post("/api/v1/auth/login", data={"username": "tx@finly.dev", "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_create_and_list_transaction(client):
    headers = _auth_headers(client)

    res = client.post("/api/v1/transactions/", json={
        "amount": "50.00",
        "type": "expense",
        "category": "food",
        "description": "Lunch",
        "transaction_date": "2024-06-01",
    }, headers=headers)
    assert res.status_code == 201

    res = client.get("/api/v1/transactions/", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_delete_transaction(client):
    headers = _auth_headers(client)
    res = client.post("/api/v1/transactions/", json={
        "amount": "20.00", "type": "expense", "category": "food",
        "description": "", "transaction_date": "2024-06-01",
    }, headers=headers)
    tx_id = res.json()["id"]
    res = client.delete(f"/api/v1/transactions/{tx_id}", headers=headers)
    assert res.status_code == 204
