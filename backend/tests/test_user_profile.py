def _register_and_login(client, email="profile@finly.dev"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "OldPass123", "full_name": "Original Name"
    })
    res = client.post("/api/v1/auth/login", data={"username": email, "password": "OldPass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_update_full_name(client):
    headers = _register_and_login(client)
    res = client.patch("/api/v1/auth/me", json={"full_name": "Updated Name"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["full_name"] == "Updated Name"


def test_update_name_reflected_in_me(client):
    headers = _register_and_login(client)
    client.patch("/api/v1/auth/me", json={"full_name": "New Name"}, headers=headers)
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.json()["full_name"] == "New Name"


def test_update_password_success(client):
    headers = _register_and_login(client)
    res = client.patch("/api/v1/auth/me", json={
        "current_password": "OldPass123",
        "new_password": "NewPass456",
    }, headers=headers)
    assert res.status_code == 200

    # Old password no longer works
    res = client.post("/api/v1/auth/login", data={"username": "profile@finly.dev", "password": "OldPass123"})
    assert res.status_code == 401

    # New password works
    res = client.post("/api/v1/auth/login", data={"username": "profile@finly.dev", "password": "NewPass456"})
    assert res.status_code == 200


def test_update_password_wrong_current(client):
    headers = _register_and_login(client)
    res = client.patch("/api/v1/auth/me", json={
        "current_password": "WrongPass",
        "new_password": "NewPass456",
    }, headers=headers)
    assert res.status_code == 400
    assert "incorrect" in res.json()["detail"].lower()


def test_update_new_password_without_current(client):
    headers = _register_and_login(client)
    res = client.patch("/api/v1/auth/me", json={"new_password": "NewPass456"}, headers=headers)
    assert res.status_code == 400
    assert "current_password" in res.json()["detail"]


def test_update_name_and_password_together(client):
    headers = _register_and_login(client)
    res = client.patch("/api/v1/auth/me", json={
        "full_name": "Combined Update",
        "current_password": "OldPass123",
        "new_password": "NewPass456",
    }, headers=headers)
    assert res.status_code == 200
    assert res.json()["full_name"] == "Combined Update"


def test_update_me_requires_auth(client):
    res = client.patch("/api/v1/auth/me", json={"full_name": "Hacker"})
    assert res.status_code == 401


def test_empty_update_is_no_op(client):
    headers = _register_and_login(client)
    res = client.patch("/api/v1/auth/me", json={}, headers=headers)
    assert res.status_code == 200
    assert res.json()["full_name"] == "Original Name"
