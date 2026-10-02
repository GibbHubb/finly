"""F47 — savings goals CRUD, over HTTP, asserting the values the UI shows."""
import pytest


def _headers(client, email):
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass12345", "full_name": "S"})
    tok = client.post("/api/v1/auth/login", data={"username": email, "password": "pass12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def h(client):
    return _headers(client, "goals@finly.dev")


def test_create_starts_at_zero_progress(client, h):
    res = client.post("/api/v1/savings-goals/", headers=h, json={
        "name": "Holiday", "target_amount": "1500.00", "deadline": "2026-12-01"})
    assert res.status_code == 201
    g = res.json()
    assert (g["name"], g["target_amount"], g["current_amount"], g["deadline"], g["progress_pct"]) == (
        "Holiday", "1500.00", "0.00", "2026-12-01", 0.0)


def test_create_rejects_a_non_positive_target(client, h):
    assert client.post("/api/v1/savings-goals/", headers=h, json={
        "name": "Nope", "target_amount": "0"}).status_code == 422


def test_patch_updates_fields_and_progress(client, h):
    gid = client.post("/api/v1/savings-goals/", headers=h, json={
        "name": "Bike", "target_amount": "800.00"}).json()["id"]

    g = client.patch(f"/api/v1/savings-goals/{gid}", headers=h, json={"current_amount": "200.00"}).json()
    assert g["current_amount"] == "200.00" and g["progress_pct"] == 25.0

    g = client.patch(f"/api/v1/savings-goals/{gid}", headers=h, json={
        "name": "E-bike", "target_amount": "300.00", "deadline": "2027-01-31"}).json()
    assert (g["name"], g["target_amount"], g["deadline"]) == ("E-bike", "300.00", "2027-01-31")
    assert g["progress_pct"] == 66.67

    # Over-saving caps progress at 100; a negative balance is clamped to zero.
    assert client.patch(f"/api/v1/savings-goals/{gid}", headers=h,
                        json={"current_amount": "450.00"}).json()["progress_pct"] == 100.0
    g = client.patch(f"/api/v1/savings-goals/{gid}", headers=h, json={"current_amount": "-50.00"}).json()
    assert g["current_amount"] == "0.00" and g["progress_pct"] == 0.0


def test_patch_refuses_a_non_positive_target(client, h):
    gid = client.post("/api/v1/savings-goals/", headers=h, json={
        "name": "Car", "target_amount": "5000.00"}).json()["id"]
    res = client.patch(f"/api/v1/savings-goals/{gid}", headers=h, json={"target_amount": "0"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Target amount must be greater than zero"
    assert client.get("/api/v1/savings-goals/", headers=h).json()[0]["target_amount"] == "5000.00"


def test_list_is_per_user_and_delete_removes(client, h):
    mine = client.post("/api/v1/savings-goals/", headers=h, json={"name": "A", "target_amount": "10"}).json()["id"]
    other = _headers(client, "other-goals@finly.dev")
    theirs = client.post("/api/v1/savings-goals/", headers=other, json={"name": "B", "target_amount": "10"}).json()["id"]

    assert [g["name"] for g in client.get("/api/v1/savings-goals/", headers=h).json()] == ["A"]

    # Another user's goal is invisible: 404 on edit and delete, and it survives.
    assert client.patch(f"/api/v1/savings-goals/{theirs}", headers=h, json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/v1/savings-goals/{theirs}", headers=h).status_code == 404
    assert len(client.get("/api/v1/savings-goals/", headers=other).json()) == 1

    assert client.delete(f"/api/v1/savings-goals/{mine}", headers=h).status_code == 204
    assert client.get("/api/v1/savings-goals/", headers=h).json() == []
