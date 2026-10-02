"""F47 — the year-in-review PDF (F28), the endpoint F38 found 500ing on Postgres.

A "returns bytes starting with %PDF" test would lift coverage and prove nothing, so these
assert the NUMBERS: the year totals against fixed rows, and the text that actually goes into
the document, captured from the reportlab story as it is built.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.models.savings_goal import SavingsGoal
from app.models.transaction import Category, Transaction, TransactionType
from app.models.user import User
from app.services import report_service


@pytest.fixture
def user(db):
    u = User(email="report@finly.dev", hashed_password="x", full_name="R")
    db.add(u)
    db.commit()
    return u


def _tx(db, user, amount, tx_type, category, on, description="", **kw):
    t = Transaction(
        user_id=user.id, amount=Decimal(amount), type=tx_type, category=category,
        description=description, transaction_date=on, currency="EUR", base_amount=Decimal(amount), **kw,
    )
    db.add(t)
    db.commit()
    return t


@pytest.fixture
def year_of_data(db, user):
    _tx(db, user, "3000.00", TransactionType.income, Category.salary, date(2025, 1, 25))
    _tx(db, user, "1200.00", TransactionType.income, Category.salary, date(2025, 7, 25))
    _tx(db, user, "450.50", TransactionType.expense, Category.food, date(2025, 2, 3), "groceries")
    _tx(db, user, "900.00", TransactionType.expense, Category.housing, date(2025, 3, 1), "rent march")
    _tx(db, user, "49.50", TransactionType.expense, Category.food, date(2025, 11, 9), "bakery")
    # Outside the year: must not count.
    _tx(db, user, "9999.00", TransactionType.expense, Category.housing, date(2024, 12, 31), "last year")
    # A split parent: its children carry the amount, the parent must not double count.
    parent = _tx(db, user, "100.00", TransactionType.expense, Category.other, date(2025, 5, 5), "split me")
    _tx(db, user, "60.00", TransactionType.expense, Category.food, date(2025, 5, 5), "child a",
        parent_transaction_id=parent.id)
    _tx(db, user, "40.00", TransactionType.expense, Category.transport, date(2025, 5, 5), "child b",
        parent_transaction_id=parent.id)
    db.add(SavingsGoal(user_id=user.id, name="Bike", target_amount=Decimal("800"),
                       current_amount=Decimal("200")))
    db.add(SavingsGoal(user_id=user.id, name="Zero target", target_amount=Decimal("0"),
                       current_amount=Decimal("5")))
    db.commit()


def test_year_totals_are_the_real_sums(db, user, year_of_data):
    t = report_service._year_totals(user.id, 2025, db)
    assert t["income"] == Decimal("4200.00")
    # 450.50 + 900 + 49.50 + (60 + 40, the split parent's 100 excluded) = 1500.00
    assert t["expenses"] == Decimal("1500.00")
    assert t["net"] == Decimal("2700.00")
    assert t["by_category"] == [
        ("housing", Decimal("900.00")),
        ("food", Decimal("560.00")),
        ("transport", Decimal("40.00")),
    ]


def test_biggest_expense_is_this_years_and_ignores_split_parents(db, user, year_of_data):
    biggest = report_service._biggest_expense(user.id, 2025, db)
    assert biggest.description == "rent march"
    assert biggest.amount == Decimal("900.00")


def test_savings_progress_handles_a_zero_target(db, user, year_of_data):
    progress = {name: (cur, tgt, pct) for name, cur, tgt, pct in report_service._savings_progress(user.id, db)}
    assert progress["Bike"] == (Decimal("200.00"), Decimal("800.00"), 25.0)
    assert progress["Zero target"][2] == 0.0


def _capture_story(monkeypatch) -> list[str]:
    """Record every Paragraph's text and every Table row as the real reportlab build runs."""
    texts: list[str] = []
    real_rl = report_service._rl

    def recording_rl():
        rl = real_rl()
        real_p, real_t = rl["P"], rl["T"]

        def P(text, *a, **k):
            texts.append(text)
            return real_p(text, *a, **k)

        def T(rows, *a, **k):
            texts.extend(" | ".join(str(c) for c in row) for row in rows)
            return real_t(rows, *a, **k)

        return {**rl, "P": P, "T": T}

    monkeypatch.setattr(report_service, "_rl", recording_rl)
    return texts


def test_pdf_carries_the_totals_categories_biggest_and_goals(db, user, year_of_data, monkeypatch):
    texts = _capture_story(monkeypatch)
    pdf = report_service.build_year_review_pdf(user.id, 2025, db)

    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
    body = "\n".join(texts)
    assert "<b>Total income:</b> 4200.00" in body
    assert "<b>Total expenses:</b> 1500.00" in body
    assert "<b>Net:</b> 2700.00" in body
    assert "housing | 900.00 | 60.0% | " + "█" * 30 in body   # the biggest category draws the full bar
    assert "food | 560.00 | 37.3%" in body
    assert "<b>900.00 EUR</b>" in body
    assert "Bike | 200.00 | 800.00 | 25%" in body


def test_pdf_for_an_empty_year_says_so(db, user, monkeypatch):
    texts = _capture_story(monkeypatch)
    report_service.build_year_review_pdf(user.id, 2019, db)
    assert "No transactions recorded for this year." in texts
    assert not any("Total income" in t for t in texts)


def test_pdf_endpoint_serves_an_attachment(client):
    client.post("/api/v1/auth/register", json={
        "email": "pdf@finly.dev", "password": "pass12345", "full_name": "P"})
    tok = client.post("/api/v1/auth/login", data={
        "username": "pdf@finly.dev", "password": "pass12345"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    client.post("/api/v1/transactions/", headers=h, json={
        "amount": "12.34", "type": "expense", "category": "food",
        "description": "lunch", "transaction_date": "2025-06-01", "currency": "EUR"})

    res = client.get("/api/v1/reports/year/2025.pdf", headers=h)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["content-disposition"] == 'attachment; filename="finly-2025-review.pdf"'
    assert res.content.startswith(b"%PDF")
