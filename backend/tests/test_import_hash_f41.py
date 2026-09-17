"""F41 — the import dedupe hash is per user.

`transactions.import_hash` carries a GLOBAL unique index while every dedup lookup is scoped to one
user, and the hash used to contain no user. So the second person to import a row anybody else
already had got a 500 and lost the whole file. The fix puts the user into the hash; the legacy
(user-less) hash is still matched, so files imported before F41 keep deduping.
"""
import io
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import sessionmaker

from app.models.transaction import Category, Transaction, TransactionType
from app.models.user import User
from app.services import import_service

LINE = "01-01-2026;Albert Heijn;NL00INGB0000000001;NL00INGB0000000099;BA;Af;2,50;Betaalautomaat;x\n"
HEADER = "Datum;Naam / Omschrijving;Rekening;Tegenrekening;Code;Af Bij;Bedrag (EUR);MutatieSoort;Mededelingen\n"


def _headers(client, email):
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass12345", "full_name": email})
    res = client.post("/api/v1/auth/login", data={"username": email, "password": "pass12345"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _import(client, headers, text):
    return client.post("/api/v1/transactions/import", headers=headers,
                       files={"file": ("x.csv", io.BytesIO(text.encode()), "text/csv")})


def _rows(db, email):
    fresh = sessionmaker(bind=db.get_bind())()
    try:
        uid = fresh.query(User.id).filter(User.email == email).scalar()
        return fresh.query(Transaction).filter(Transaction.user_id == uid).count()
    finally:
        fresh.close()


def test_two_users_import_the_same_row(client, db):
    a, b = _headers(client, "a@f41.dev"), _headers(client, "b@f41.dev")

    ra = _import(client, a, HEADER + LINE)
    rb = _import(client, b, HEADER + LINE)

    assert ra.status_code == 200 and ra.json()["imported"] == 1
    assert rb.status_code == 200, rb.text  # was a 500 (UNIQUE constraint failed)
    assert rb.json() == {"imported": 1, "skipped_duplicates": 0, "errors": []}
    assert _rows(db, "a@f41.dev") == 1 and _rows(db, "b@f41.dev") == 1


def test_reimporting_the_same_file_still_skips(client, db):  # the dedupe that must keep working
    a = _headers(client, "a@f41.dev")
    _import(client, a, HEADER + LINE)

    res = _import(client, a, HEADER + LINE)

    assert res.json() == {"imported": 0, "skipped_duplicates": 1, "errors": []}
    assert _rows(db, "a@f41.dev") == 1


def test_a_row_imported_before_f41_still_dedupes(client, db):
    a = _headers(client, "a@f41.dev")
    uid = db.query(User.id).filter(User.email == "a@f41.dev").scalar()
    d, amt, desc = date(2026, 1, 1), Decimal("2.50"), "Albert Heijn"
    db.add(Transaction(user_id=uid, amount=amt, type=TransactionType.expense, category=Category.food,
                       description=desc, transaction_date=d, base_amount=amt,
                       import_hash=import_service._legacy_hash(d, amt, desc)))
    db.commit()

    res = _import(client, a, HEADER + LINE)

    assert res.json()["skipped_duplicates"] == 1 and res.json()["imported"] == 0
    assert _rows(db, "a@f41.dev") == 1


def test_mapped_import_two_users_same_row(client, db):
    import json
    csv = b"Date,Label,Amount\n2026-01-01,Albert Heijn,-2.50\n"
    mapping = {"date_col": "Date", "amount_col": "Amount", "description_col": "Label",
               "date_format": "YYYY-MM-DD", "decimal_format": "dot"}
    for email in ("a@f41.dev", "b@f41.dev"):
        res = client.post("/api/v1/transactions/import/commit", headers=_headers(client, email),
                          files={"file": ("x.csv", io.BytesIO(csv), "text/csv")},
                          data={"mapping": json.dumps(mapping)})
        assert res.status_code == 200 and res.json()["imported"] == 1, res.text


def test_a_racing_duplicate_is_a_409_not_a_500_and_imports_nothing(client, db, monkeypatch):
    """Simulate a double-clicked upload: the dedup check passes, but by commit time the same rows
    exist. The unique index is the real guard; it must surface as a clear 409 and a rollback."""
    a = _headers(client, "a@f41.dev")
    two_lines = HEADER + LINE + LINE.replace("Albert Heijn", "Jumbo")
    assert _import(client, a, HEADER + LINE).json()["imported"] == 1  # the 'other request' won

    real = import_service.find_existing_import
    monkeypatch.setattr(import_service, "find_existing_import",
                        lambda *args: (real(*args)[0], False))  # the check sees nothing yet

    res = _import(client, a, two_lines)

    assert res.status_code == 409, res.text
    assert "nothing was imported" in res.json()["detail"]
    assert _rows(db, "a@f41.dev") == 1  # the Jumbo row did not half-import


def test_a_bad_row_in_a_long_file_is_named_and_the_rest_import(client, db):
    a = _headers(client, "a@f41.dev")
    lines = [LINE.replace("Albert Heijn", f"Shop {i}") for i in range(100)]
    lines[49] = "99-99-2026;Broken;;;BA;Af;not-a-number;x;x\n"  # row 50 of the data = file row 51

    res = _import(client, a, HEADER + "".join(lines))

    body = res.json()
    assert res.status_code == 200
    assert body["imported"] == 99 and len(body["errors"]) == 1
    assert body["errors"][0].startswith("Row 51:")
    assert _rows(db, "a@f41.dev") == 99


def test_a_different_constraint_failure_is_not_disguised_as_a_duplicate(db, monkeypatch):  # /code-review on F41
    import pytest
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    def boom():
        raise IntegrityError("INSERT", {}, Exception("FOREIGN KEY constraint failed"))
    monkeypatch.setattr(db, "commit", boom)
    with pytest.raises(IntegrityError):
        import_service.commit_import(db)

    def clash():
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: transactions.import_hash"))
    monkeypatch.setattr(db, "commit", clash)
    with pytest.raises(HTTPException) as e:
        import_service.commit_import(db)
    assert e.value.status_code == 409
