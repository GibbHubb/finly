"""Tests for the generic mapped CSV import — F9 wizard path."""
import io
import json


def _auth_headers(client, email="mapper@finly.dev"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "pass123", "full_name": "Mapper User",
    })
    res = client.post("/api/v1/auth/login", data={"username": email, "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# A simple generic CSV — comma-delimited, ISO dates, dot-decimal, signed amounts.
GENERIC_CSV = (
    "Date,Label,Amount,Category\n"
    "2026-03-05,Groceries,-45.20,food\n"
    "2026-03-08,Spotify,-10.99,entertainment\n"
    "2026-03-10,Salary,2500.00,salary\n"
    "2026-03-12,Petrol,-65.30,transport\n"
).encode()


EURO_CSV = (
    "Datum;Omschrijving;Bedrag\n"
    "05-03-2026;Albert Heijn;-45,20\n"
    "08-03-2026;Spotify;-10,99\n"
).encode()


def _preview(client, headers, csv_bytes, filename="export.csv"):
    return client.post(
        "/api/v1/transactions/import/preview",
        files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")},
        headers=headers,
    )


def _commit(client, headers, csv_bytes, mapping: dict, filename="export.csv"):
    return client.post(
        "/api/v1/transactions/import/commit",
        files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")},
        data={"mapping": json.dumps(mapping)},
        headers=headers,
    )


def test_preview_returns_headers_and_sample(client):
    headers = _auth_headers(client)
    res = _preview(client, headers, GENERIC_CSV)
    assert res.status_code == 200
    body = res.json()
    assert body["headers"] == ["Date", "Label", "Amount", "Category"]
    assert body["delimiter"] == ","
    assert len(body["sample_rows"]) == 4
    assert body["sample_rows"][0]["Label"] == "Groceries"
    assert body["saved_mapping"] is None


def test_preview_requires_auth(client):
    res = client.post("/api/v1/transactions/import/preview")
    assert res.status_code == 401


def test_commit_imports_and_persists_mapping(client):
    headers = _auth_headers(client)
    mapping = {
        "date_col": "Date",
        "amount_col": "Amount",
        "description_col": "Label",
        "category_col": "Category",
        "date_format": "YYYY-MM-DD",
        "decimal_format": "dot",
    }
    res = _commit(client, headers, GENERIC_CSV, mapping)
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 4
    assert body["skipped_duplicates"] == 0
    assert body["errors"] == []

    # Mapping should now be persisted and returned by the mapping endpoint
    res = client.get("/api/v1/transactions/import/mapping", headers=headers)
    assert res.status_code == 200
    saved = res.json()
    assert saved is not None
    assert saved["date_col"] == "Date"
    assert saved["category_col"] == "Category"

    # A second preview should surface the saved mapping
    res = _preview(client, headers, GENERIC_CSV)
    assert res.json()["saved_mapping"]["date_col"] == "Date"


def test_commit_dedupes_on_reimport(client):
    headers = _auth_headers(client)
    mapping = {
        "date_col": "Date", "amount_col": "Amount", "description_col": "Label",
        "date_format": "YYYY-MM-DD", "decimal_format": "dot",
    }
    _commit(client, headers, GENERIC_CSV, mapping)
    res = _commit(client, headers, GENERIC_CSV, mapping)
    body = res.json()
    assert body["imported"] == 0
    assert body["skipped_duplicates"] == 4


def test_commit_expense_vs_income_from_sign(client):
    headers = _auth_headers(client)
    mapping = {
        "date_col": "Date", "amount_col": "Amount", "description_col": "Label",
        "category_col": "Category",
        "date_format": "YYYY-MM-DD", "decimal_format": "dot",
    }
    _commit(client, headers, GENERIC_CSV, mapping)
    txs = client.get("/api/v1/transactions/", headers=headers).json()
    types = {t["description"]: t["type"] for t in txs}
    assert types["Groceries"] == "expense"
    assert types["Salary"] == "income"


def test_commit_euro_format_with_auto_delimiter(client):
    headers = _auth_headers(client)
    mapping = {
        "date_col": "Datum",
        "amount_col": "Bedrag",
        "description_col": "Omschrijving",
        "date_format": "DD-MM-YYYY",
        "decimal_format": "comma",
        # No delimiter specified — should auto-detect ';'
    }
    res = _commit(client, headers, EURO_CSV, mapping)
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 2
    assert body["errors"] == []


def test_commit_bad_column_fails_cleanly(client):
    headers = _auth_headers(client)
    mapping = {
        "date_col": "Nope",   # not a real column
        "amount_col": "Amount", "description_col": "Label",
        "date_format": "YYYY-MM-DD", "decimal_format": "dot",
    }
    res = _commit(client, headers, GENERIC_CSV, mapping)
    body = res.json()
    assert body["imported"] == 0
    assert body["errors"]
    assert "Nope" in body["errors"][0]


def test_commit_rejects_malformed_mapping(client):
    headers = _auth_headers(client)
    res = client.post(
        "/api/v1/transactions/import/commit",
        files={"file": ("x.csv", io.BytesIO(GENERIC_CSV), "text/csv")},
        data={"mapping": "not-json"},
        headers=headers,
    )
    assert res.status_code == 422


def test_mapping_endpoint_returns_null_by_default(client):
    headers = _auth_headers(client)
    res = client.get("/api/v1/transactions/import/mapping", headers=headers)
    assert res.status_code == 200
    assert res.json() is None
