"""Tests for the F11 categorisation-rules engine."""
import io
import json


def _auth_headers(client, email="rules@finly.dev"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "pass123", "full_name": "Rules User",
    })
    res = client.post("/api/v1/auth/login", data={"username": email, "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_rule(client, headers, match_type, match_value, category, priority=100, enabled=True):
    return client.post("/api/v1/categorisation-rules/", headers=headers, json={
        "match_type": match_type,
        "match_value": match_value,
        "category": category,
        "priority": priority,
        "enabled": enabled,
    })


def test_requires_auth(client):
    res = client.get("/api/v1/categorisation-rules/")
    assert res.status_code == 401


def test_crud_roundtrip(client):
    headers = _auth_headers(client)
    res = _create_rule(client, headers, "contains", "Albert Heijn", "food")
    assert res.status_code == 201
    rule = res.json()
    rule_id = rule["id"]
    assert rule["match_type"] == "contains"

    # List
    res = client.get("/api/v1/categorisation-rules/", headers=headers)
    assert len(res.json()) == 1

    # Update — flip enabled
    res = client.patch(f"/api/v1/categorisation-rules/{rule_id}", headers=headers, json={"enabled": False})
    assert res.status_code == 200
    assert res.json()["enabled"] is False

    # Delete
    res = client.delete(f"/api/v1/categorisation-rules/{rule_id}", headers=headers)
    assert res.status_code == 204
    res = client.get("/api/v1/categorisation-rules/", headers=headers)
    assert res.json() == []


def test_invalid_regex_rejected(client):
    headers = _auth_headers(client)
    res = _create_rule(client, headers, "regex", "[unclosed", "food")
    assert res.status_code == 422
    assert "regex" in res.json()["detail"].lower()


def test_rule_applied_on_manual_transaction_via_recategorise(client):
    """Transactions created via POST / always default through the existing
    _infer_category — ensure recategorise endpoint applies rules retroactively."""
    headers = _auth_headers(client)
    # Add an expense whose description does not hit any hardcoded keyword
    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "12.50", "type": "expense", "category": "other",
        "description": "Weird Merchant XYZ", "transaction_date": "2026-03-05",
    })
    _create_rule(client, headers, "contains", "Weird Merchant", "entertainment")

    res = client.post("/api/v1/categorisation-rules/apply", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"updated": 1}

    txs = client.get("/api/v1/transactions/", headers=headers).json()
    assert txs[0]["category"] == "entertainment"


def test_rule_applied_on_csv_import(client):
    """Rules should override _infer_category during a generic CSV import."""
    headers = _auth_headers(client)
    _create_rule(client, headers, "contains", "NOTAWORD", "health", priority=10)

    csv_bytes = (
        "Date,Label,Amount\n"
        "2026-03-05,Contains NOTAWORD thing,-20.00\n"
    ).encode()
    res = client.post(
        "/api/v1/transactions/import/commit",
        files={"file": ("x.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"mapping": json.dumps({
            "date_col": "Date", "amount_col": "Amount", "description_col": "Label",
            "date_format": "YYYY-MM-DD", "decimal_format": "dot",
        })},
        headers=headers,
    )
    assert res.json()["imported"] == 1
    txs = client.get("/api/v1/transactions/", headers=headers).json()
    assert txs[0]["category"] == "health"


def test_priority_order(client):
    """Lower priority number wins."""
    headers = _auth_headers(client)
    _create_rule(client, headers, "contains", "ambiguous", "food", priority=100)
    _create_rule(client, headers, "contains", "ambiguous", "transport", priority=10)

    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "5.00", "type": "expense", "category": "other",
        "description": "an ambiguous charge", "transaction_date": "2026-03-05",
    })
    client.post("/api/v1/categorisation-rules/apply", headers=headers)
    txs = client.get("/api/v1/transactions/", headers=headers).json()
    assert txs[0]["category"] == "transport"


def test_disabled_rule_skipped(client):
    headers = _auth_headers(client)
    res = _create_rule(client, headers, "contains", "SpecificVendor", "shopping", enabled=False)
    rule = res.json()
    assert rule["enabled"] is False

    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "9.99", "type": "expense", "category": "other",
        "description": "SpecificVendor xyz", "transaction_date": "2026-03-05",
    })
    client.post("/api/v1/categorisation-rules/apply", headers=headers)
    txs = client.get("/api/v1/transactions/", headers=headers).json()
    assert txs[0]["category"] == "other"


def test_match_types(client):
    headers = _auth_headers(client)
    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "1.00", "type": "expense", "category": "other",
        "description": "Spotify Premium", "transaction_date": "2026-03-05",
    })
    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "1.00", "type": "expense", "category": "other",
        "description": "BP PUMP 01", "transaction_date": "2026-03-05",
    })
    client.post("/api/v1/transactions/", headers=headers, json={
        "amount": "1.00", "type": "expense", "category": "other",
        "description": "regex-target-123", "transaction_date": "2026-03-05",
    })

    _create_rule(client, headers, "starts_with", "Spotify", "entertainment", priority=5)
    _create_rule(client, headers, "equals", "BP PUMP 01", "transport", priority=5)
    _create_rule(client, headers, "regex", r"regex-target-\d+", "shopping", priority=5)

    client.post("/api/v1/categorisation-rules/apply", headers=headers)
    txs = client.get("/api/v1/transactions/", headers=headers).json()
    by_desc = {t["description"]: t["category"] for t in txs}
    assert by_desc["Spotify Premium"] == "entertainment"
    assert by_desc["BP PUMP 01"] == "transport"
    assert by_desc["regex-target-123"] == "shopping"
