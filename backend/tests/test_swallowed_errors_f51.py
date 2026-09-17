"""F51 — the except blocks that used to swallow silently now degrade AND say so."""
import io
import json
import logging
from pathlib import Path

from app.services import bank_sync_service

FIXTURES = Path(__file__).parent / "fixtures"


def _h(client):
    client.post("/api/v1/auth/register", json={"email": "f51@finly.dev", "password": "pass12345", "full_name": "F51"})
    r = client.post("/api/v1/auth/login", data={"username": "f51@finly.dev", "password": "pass12345"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_a_recurring_tag_failure_keeps_the_import_and_is_logged(client, db, monkeypatch, caplog):
    import app.services.recurring_service as rs

    def boom(user_id, db):
        raise RuntimeError("detector exploded")
    monkeypatch.setattr(rs, "apply_recurring_tags", boom)
    h = _h(client)
    with caplog.at_level(logging.ERROR, logger="app.services.import_service"):
        r = client.post("/api/v1/transactions/import", headers=h,
                        files={"file": ("x.csv", io.BytesIO((FIXTURES / "ing_sample.csv").read_bytes()), "text/csv")})
    assert r.status_code == 200 and r.json()["imported"] == 6
    assert "recurring-tag detection failed" in caplog.text and "detector exploded" in caplog.text
    # the session still works after the rollback: the rows are readable in the same app
    assert len(client.get("/api/v1/transactions/", headers=h).json()) == 6


def test_an_unparseable_bank_amount_is_skipped_and_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.bank_sync_service"):
        out = bank_sync_service._normalise_tx({"transactionAmount": {"amount": "12,34,56", "currency": "EUR"},
                                               "bookingDate": "2026-03-05"})
    assert out is None and "unparseable amount" in caplog.text


def test_a_parseable_bank_amount_is_not_logged(caplog):  # control
    with caplog.at_level(logging.WARNING, logger="app.services.bank_sync_service"):
        out = bank_sync_service._normalise_tx({"transactionAmount": {"amount": "-12.34", "currency": "EUR"},
                                               "bookingDate": "2026-03-05"})
    assert out is not None and caplog.text == ""


def test_bad_mapping_json_is_still_a_422(client, db):
    h = _h(client)
    r = client.post("/api/v1/transactions/import/commit", headers=h,
                    files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
                    data={"mapping": "{not json"})
    assert r.status_code == 422 and "Invalid mapping JSON" in r.text
