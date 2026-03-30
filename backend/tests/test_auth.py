def test_register_and_login(client):
    # Register
    res = client.post("/api/v1/auth/register", json={
        "email": "test@finly.dev",
        "password": "SecurePass123",
        "full_name": "Test User",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "test@finly.dev"

    # Login
    res = client.post("/api/v1/auth/login", data={
        "username": "test@finly.dev",
        "password": "SecurePass123",
    })
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_duplicate_email(client):
    payload = {"email": "dupe@finly.dev", "password": "pass", "full_name": "Dupe"}
    client.post("/api/v1/auth/register", json=payload)
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 400


def test_me_requires_auth(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
