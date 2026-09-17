"""F57 — imports follow F55's rule: during an FX outage, refuse and write nothing.

Before F57 all three import paths could store an unpriced row:
  * CSV import and the mapped import stored NULL `base_amount` for any row whose rate failed,
    inside an otherwise successful batch commit;
  * bank sync never set `base_amount` at all, outage or not.
A NULL reads back as the raw foreign amount (F56), so the totals were silently wrong.

Owner rule (F55, 2026-09-16): when a needed rate is unavailable, refuse and change nothing.
Each refusal test has a control that proves the outage was reached, and each path has a
positive control showing the same input imports cleanly once rates are back.
"""
import io
import json
from decimal import Decimal
from pathlib import Path
from unittest import mock

from sqlalchemy.orm import sessionmaker

from app.models.bank_connection import BankConnection
from app.models.transaction import Transaction
from app.models.user import User
from tests.test_fx_outage_f55 import _start_outage, fx  # noqa: F401 — the shared switchable Frankfurter

FIXTURES = Path(__file__).parent / "fixtures"
EMAIL = "f57@finly.dev"

MAPPED_CSV = (
    "Date,Label,Amount\n"
    "2026-03-05,Groceries,-45.20\n"
    "2026-03-08,Spotify,-10.99\n"
).encode()
MAPPING = {"date_col": "Date", "amount_col": "Amount", "description_col": "Label",
           "date_format": "YYYY-MM-DD", "decimal_format": "dot"}


def _user(client, base_currency):
    client.post("/api/v1/auth/register", json={"email": EMAIL, "password": "pass12345", "full_name": "F57"})
    res = client.post("/api/v1/auth/login", data={"username": EMAIL, "password": "pass12345"})
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    if base_currency != "EUR":
        r = client.patch("/api/v1/auth/me", headers=headers, json={"base_currency": base_currency})
        assert r.status_code == 200, r.text
    return headers


def _committed_rows(db):
    """What is COMMITTED, read through a fresh session: [(amount, base_amount)]."""
    fresh = sessionmaker(bind=db.get_bind())()
    try:
        uid = fresh.query(User.id).filter(User.email == EMAIL).scalar()
        return sorted((t.amount, t.base_amount) for t in fresh.query(Transaction).filter(Transaction.user_id == uid))
    finally:
        fresh.close()


def _csv(client, headers, content):
    return client.post("/api/v1/transactions/import", headers=headers,
                       files={"file": ("export.csv", io.BytesIO(content), "text/csv")})


def _mapped(client, headers, content):
    return client.post("/api/v1/transactions/import/commit", headers=headers,
                       files={"file": ("export.csv", io.BytesIO(content), "text/csv")},
                       data={"mapping": json.dumps(MAPPING)})


# ── CSV import ──────────────────────────────────────────────────────────────
def test_csv_import_is_refused_during_an_outage_and_imports_nothing(client, db, fx):
    headers = _user(client, "USD")
    _start_outage(db, fx)

    res = _csv(client, headers, (FIXTURES / "ing_sample.csv").read_bytes())

    assert res.status_code == 503
    assert "nothing was imported" in res.json()["detail"]
    assert fx["calls"] > 0, "the outage was never reached — this test proves nothing"
    assert _committed_rows(db) == []


def test_csv_import_after_the_outage_prices_every_row(client, db, fx):  # positive control
    headers = _user(client, "USD")
    _start_outage(db, fx)
    assert _csv(client, headers, (FIXTURES / "ing_sample.csv").read_bytes()).status_code == 503
    fx["mode"] = "ok"

    res = _csv(client, headers, (FIXTURES / "ing_sample.csv").read_bytes())

    assert res.status_code == 200 and res.json()["imported"] == 6
    rows = _committed_rows(db)
    assert len(rows) == 6 and all(base is not None for _, base in rows)
    # EUR 47.83 at 1.10 USD/EUR, so the base is the converted figure, not the raw amount.
    assert (Decimal("47.83"), Decimal("52.61")) in rows


def test_csv_import_needs_no_rate_when_base_is_eur(client, db, fx):  # control: no false refusals
    headers = _user(client, "EUR")
    _start_outage(db, fx)

    res = _csv(client, headers, (FIXTURES / "ing_sample.csv").read_bytes())

    assert res.status_code == 200 and res.json()["imported"] == 6
    assert all(base == amount for amount, base in _committed_rows(db))


def test_the_same_row_twice_in_one_file_is_a_duplicate_not_a_500(client, db, fx):
    headers = _user(client, "EUR")
    lines = (FIXTURES / "ing_sample.csv").read_bytes().splitlines(keepends=True)
    doubled = b"".join(lines[:2] + lines[1:2])  # header, row 1, row 1 again

    res = _csv(client, headers, doubled)

    assert res.status_code == 200, res.text
    assert res.json()["imported"] == 1 and res.json()["skipped_duplicates"] == 1
    assert len(_committed_rows(db)) == 1


# ── mapped import ───────────────────────────────────────────────────────────
def test_mapped_import_is_refused_during_an_outage_and_imports_nothing(client, db, fx):
    headers = _user(client, "GBP")
    _start_outage(db, fx)

    res = _mapped(client, headers, MAPPED_CSV)

    assert res.status_code == 503
    assert fx["calls"] > 0
    assert _committed_rows(db) == []


def test_mapped_import_after_the_outage_prices_every_row(client, db, fx):  # positive control
    headers = _user(client, "GBP")
    res = _mapped(client, headers, MAPPED_CSV)
    assert res.status_code == 200 and res.json()["imported"] == 2
    assert all(base is not None and base != amount for amount, base in _committed_rows(db))


# ── bank sync ───────────────────────────────────────────────────────────────
def _conn(db, client, base_currency):
    _user(client, base_currency)
    uid = db.query(User.id).filter(User.email == EMAIL).scalar()
    conn = BankConnection(user_id=uid, requisition_id="req-f57", account_id="acc-f57",
                          institution_id="TEST", status="active")
    db.add(conn)
    db.commit()
    return conn


BOOKED = {"transactions": {"booked": [
    {"transactionAmount": {"amount": "-20.00", "currency": "EUR"}, "bookingDate": "2026-03-05",
     "remittanceInformationUnstructured": "Coffee"},
    {"transactionAmount": {"amount": "-30.00", "currency": "EUR"}, "bookingDate": "2026-03-06",
     "remittanceInformationUnstructured": "Lunch"},
]}}


def _sync(conn, db):
    from app.services.bank_sync_service import sync_connection
    with mock.patch("app.services.bank_sync_service.gc.fetch_transactions", return_value=BOOKED):
        result = sync_connection(conn, db)
    db.commit()  # the caller commits (sync_all_active / the endpoint)
    return result


def test_bank_sync_during_an_outage_adds_nothing_and_stays_retryable(client, db, fx):
    conn = _conn(db, client, "USD")
    _start_outage(db, fx)

    result = _sync(conn, db)

    assert result["inserted"] == 0 and "unavailable" in result["error"]
    assert fx["calls"] > 0
    assert _committed_rows(db) == []
    # sync_all_active only retries active/pending connections, so this must not become "error".
    assert conn.status == "active"


def test_bank_sync_stores_a_base_amount(client, db, fx):  # the path used to store NULL always
    conn = _conn(db, client, "USD")

    result = _sync(conn, db)

    assert result["inserted"] == 2 and result["error"] is None
    assert _committed_rows(db) == [(Decimal("20.00"), Decimal("22.00")), (Decimal("30.00"), Decimal("33.00"))]


def test_two_connections_on_one_account_do_not_insert_the_same_row_twice(client, db, fx):
    """/code-review on F57: dedup is per connection, and autoflush is off, so a reconnect (two
    active connections, same account) inserted each row twice and failed the whole run's commit."""
    from app.services.bank_sync_service import sync_connection
    first = _conn(db, client, "EUR")
    second = BankConnection(user_id=first.user_id, requisition_id="req-f57b", account_id="acc-f57",
                            institution_id="TEST", status="active")
    db.add(second)
    db.commit()
    with mock.patch("app.services.bank_sync_service.gc.fetch_transactions", return_value=BOOKED):
        a = sync_connection(first, db)
        b = sync_connection(second, db)
    db.commit()
    assert (a["inserted"], b["inserted"], b["skipped"]) == (2, 0, 2)
    assert len(_committed_rows(db)) == 2
