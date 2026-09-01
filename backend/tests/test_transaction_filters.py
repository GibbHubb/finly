def _auth_headers(client):
    client.post("/api/v1/auth/register", json={
        "email": "filter@finly.dev", "password": "pass123", "full_name": "Filter User"
    })
    res = client.post("/api/v1/auth/login", data={"username": "filter@finly.dev", "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _tx(client, headers, amount, tx_type, category, date):
    return client.post("/api/v1/transactions/", json={
        "amount": amount, "type": tx_type, "category": category,
        "description": "", "transaction_date": date,
    }, headers=headers)


def _seed(client, headers):
    """Seed a predictable set of transactions across two months."""
    _tx(client, headers, "1000.00", "income",  "salary",  "2024-06-01")
    _tx(client, headers, "200.00",  "expense", "food",    "2024-06-15")
    _tx(client, headers, "80.00",   "expense", "transport","2024-06-20")
    _tx(client, headers, "500.00",  "income",  "freelance","2024-07-05")
    _tx(client, headers, "150.00",  "expense", "food",    "2024-07-10")


# --- date range filters ---

def test_filter_date_from(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?date_from=2024-07-01", headers=headers)
    assert res.status_code == 200
    dates = [t["transaction_date"] for t in res.json()]
    assert all(d >= "2024-07-01" for d in dates)
    assert len(dates) == 2


def test_filter_date_to(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?date_to=2024-06-30", headers=headers)
    assert res.status_code == 200
    dates = [t["transaction_date"] for t in res.json()]
    assert all(d <= "2024-06-30" for d in dates)
    assert len(dates) == 3


def test_filter_date_range(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?date_from=2024-06-15&date_to=2024-06-30", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 2


# --- category filter ---

def test_filter_category(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?category=food", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert all(t["category"] == "food" for t in data)


# --- type filter ---

def test_filter_type_income(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?type=income", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert all(t["type"] == "income" for t in data)


def test_filter_type_expense(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?type=expense", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3
    assert all(t["type"] == "expense" for t in data)


# --- combined filters ---

def test_filter_combined_type_and_date(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?type=expense&date_from=2024-07-01", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["category"] == "food"
    assert data[0]["transaction_date"] == "2024-07-10"


def test_filter_combined_category_and_type(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?category=salary&type=income", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_filter_no_results(client):
    headers = _auth_headers(client)
    _seed(client, headers)
    res = client.get("/api/v1/transactions/?category=health", headers=headers)
    assert res.status_code == 200
    assert res.json() == []
