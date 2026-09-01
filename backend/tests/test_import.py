"""Tests for POST /api/v1/transactions/import"""
import io
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _auth_headers(client):
    client.post("/api/v1/auth/register", json={
        "email": "imp@finly.dev", "password": "pass123", "full_name": "Imp User"
    })
    res = client.post("/api/v1/auth/login", data={"username": "imp@finly.dev", "password": "pass123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _upload(client, headers, csv_bytes: bytes, filename="export.csv"):
    return client.post(
        "/api/v1/transactions/import",
        files={"file": (filename, io.BytesIO(csv_bytes), "text/csv")},
        headers=headers,
    )


def test_import_ing_csv(client):
    """ING fixture: 5 expenses + 1 income should import correctly."""
    headers = _auth_headers(client)
    csv_bytes = (FIXTURES / "ing_sample.csv").read_bytes()

    res = _upload(client, headers, csv_bytes)
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 6
    assert body["skipped_duplicates"] == 0
    assert body["errors"] == []

    # Verify transactions were created
    txs = client.get("/api/v1/transactions/", headers=headers).json()
    assert len(txs) == 6


def test_import_ing_deduplication(client):
    """Re-importing the same ING file skips all rows as duplicates."""
    headers = _auth_headers(client)
    csv_bytes = (FIXTURES / "ing_sample.csv").read_bytes()

    _upload(client, headers, csv_bytes)
    res = _upload(client, headers, csv_bytes)
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 0
    assert body["skipped_duplicates"] == 6


def test_import_abn_csv(client):
    """ABN AMRO fixture: 3 expenses + 1 income should import correctly."""
    headers = _auth_headers(client)
    csv_bytes = (FIXTURES / "abn_sample.csv").read_bytes()

    res = _upload(client, headers, csv_bytes)
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 4
    assert body["skipped_duplicates"] == 0


def test_import_unknown_format(client):
    """Unknown CSV format returns a clear error message, not a 500."""
    headers = _auth_headers(client)
    bad_csv = b"foo,bar,baz\n1,2,3\n"

    res = _upload(client, headers, bad_csv)
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 0
    assert len(body["errors"]) > 0
    assert "Unrecognised" in body["errors"][0]


def test_import_partial_row_errors(client):
    """A row with an unparseable date should produce a row error but not abort the import."""
    headers = _auth_headers(client)
    bad_row = (
        "Datum;Naam / Omschrijving;Rekening;Tegenrekening;Code;Af Bij;Bedrag (EUR);MutatieSoort;Mededelingen\n"
        "NOT-A-DATE;Albert Heijn;NL00INGB0000000001;NL00INGB0000000099;BA;Af;10,00;Betaalautomaat;\n"
        "20-03-2026;Jumbo;NL00INGB0000000001;NL00INGB0000000099;BA;Af;25,00;Betaalautomaat;\n"
    )
    res = _upload(client, headers, bad_row.encode())
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 1
    assert len(body["errors"]) == 1
