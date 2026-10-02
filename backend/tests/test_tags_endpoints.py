"""F47 — tag CRUD and assignment over HTTP (F29)."""
import pytest


def _headers(client, email):
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass12345", "full_name": "T"})
    tok = client.post("/api/v1/auth/login", data={"username": email, "password": "pass12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def h(client):
    return _headers(client, "tags@finly.dev")


def _tx(client, h):
    return client.post("/api/v1/transactions/", headers=h, json={
        "amount": "9.99", "type": "expense", "category": "entertainment",
        "description": "stream", "transaction_date": "2026-02-01", "currency": "EUR"}).json()["id"]


def test_create_normalises_and_dedupes(client, h):
    a = client.post("/api/v1/tags", headers=h, json={"name": "  Holiday "}).json()
    b = client.post("/api/v1/tags", headers=h, json={"name": "HOLIDAY"}).json()
    assert a == b and a["name"] == "holiday"
    client.post("/api/v1/tags", headers=h, json={"name": "Coffee"})
    assert [t["name"] for t in client.get("/api/v1/tags", headers=h).json()] == ["coffee", "holiday"]


def test_create_rejects_a_blank_name(client, h):
    res = client.post("/api/v1/tags", headers=h, json={"name": "   "})
    assert res.status_code == 422 and res.json()["detail"] == "Tag name is required"


def test_tags_are_per_user(client, h):
    client.post("/api/v1/tags", headers=h, json={"name": "mine"})
    other = _headers(client, "tags-other@finly.dev")
    theirs = client.post("/api/v1/tags", headers=other, json={"name": "mine"}).json()
    assert [t["name"] for t in client.get("/api/v1/tags", headers=other).json()] == ["mine"]
    assert client.delete(f"/api/v1/tags/{theirs['id']}", headers=h).status_code == 404
    assert len(client.get("/api/v1/tags", headers=other).json()) == 1


def test_delete_removes_the_tag(client, h):
    tid = client.post("/api/v1/tags", headers=h, json={"name": "gone"}).json()["id"]
    assert client.delete(f"/api/v1/tags/{tid}", headers=h).status_code == 204
    assert client.get("/api/v1/tags", headers=h).json() == []


def test_assign_finds_or_creates_and_is_idempotent(client, h):
    tx = _tx(client, h)
    assert [t["name"] for t in client.post(f"/api/v1/tags/assign/{tx}", headers=h, json={"name": "Sub"}).json()] == ["sub"]
    again = client.post(f"/api/v1/tags/assign/{tx}", headers=h, json={"name": "sub"}).json()
    assert [t["name"] for t in again] == ["sub"]
    both = client.post(f"/api/v1/tags/assign/{tx}", headers=h, json={"name": "monthly"}).json()
    assert sorted(t["name"] for t in both) == ["monthly", "sub"]
    # The tag was created once and is now listed.
    assert sorted(t["name"] for t in client.get("/api/v1/tags", headers=h).json()) == ["monthly", "sub"]

    sub_id = next(t["id"] for t in both if t["name"] == "sub")
    left = client.delete(f"/api/v1/tags/assign/{tx}/{sub_id}", headers=h).json()
    assert [t["name"] for t in left] == ["monthly"]


def test_assign_rejects_blank_names_and_foreign_transactions(client, h):
    tx = _tx(client, h)
    res = client.post(f"/api/v1/tags/assign/{tx}", headers=h, json={"name": " "})
    assert res.status_code == 422 and res.json()["detail"] == "Tag name must not be empty"

    other = _headers(client, "tags-intruder@finly.dev")
    assert client.post(f"/api/v1/tags/assign/{tx}", headers=other, json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/v1/tags/assign/{tx}/1", headers=other).status_code == 404
