"""F45 — the rules the API enforced in Python are now enforced by the database too.

Both races are made deterministic: the budget test holds two real threads at a barrier
between their SELECT and their INSERT (exactly what a double-submit does), and the FX test writes the same date twice (exactly what two concurrent conversions do).
Each fails on a revert: without the constraint the budget test finds two rows; without the
IntegrityError handling it gets an IntegrityError instead of a 409; without the
conflict-tolerant insert the FX test raises.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.budget import Budget
from app.models.fx_rate import FxRate
from app.models.user import User
from app.schemas.budget import BudgetCreate
from app.services import budgets as budgets_service
from app.services import rates_service


def _user(db) -> int:
    u = User(email="f45@finly.dev", hashed_password="x", full_name="F45")
    db.add(u)
    db.commit()
    return u.id


def test_concurrent_duplicate_budget_leaves_one_row_and_one_409(db):
    """Two real threads, held at a barrier between their SELECT and their INSERT, so both
    pass the pre-check before either commits — the interleaving a double-submit produces."""
    uid = _user(db)
    data = BudgetCreate(category="food", limit_amount=Decimal("300.00"), month=6, year=2026)
    barrier = threading.Barrier(2, timeout=10)

    def request(_):
        s = Session(bind=db.get_bind())
        real_add = s.add

        def add_after_both_checked(obj, *a, **k):
            barrier.wait()  # both SELECTs have run and seen no budget
            return real_add(obj, *a, **k)

        s.add = add_after_both_checked
        try:
            budgets_service.create_budget(data, uid, s)
            return 201
        except HTTPException as exc:
            assert exc.detail == "Budget for this category/month already exists"
            return exc.status_code
        finally:
            s.close()

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(request, range(2)))

    assert codes == [201, 409]
    db.expire_all()
    assert db.query(Budget).filter(Budget.user_id == uid).count() == 1


def test_budget_uniqueness_is_a_database_constraint(db):
    """Control: bypass the service entirely; the database itself refuses the second row."""
    uid = _user(db)
    row = dict(user_id=uid, category="food", limit_amount=Decimal("1"), month=1, year=2026)
    db.add(Budget(**row))
    db.commit()
    db.add(Budget(**row))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_sequential_duplicate_budget_is_still_409_over_http(client):
    client.post("/api/v1/auth/register", json={
        "email": "f45h@finly.dev", "password": "pass12345", "full_name": "x"})
    tok = client.post("/api/v1/auth/login", data={
        "username": "f45h@finly.dev", "password": "pass12345"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    body = {"category": "food", "limit_amount": "300.00", "month": 6, "year": 2026}
    assert client.post("/api/v1/budgets/", json=body, headers=h).status_code == 201
    second = client.post("/api/v1/budgets/", json=body, headers=h)
    assert second.status_code == 409
    assert second.json()["detail"] == "Budget for this category/month already exists"
    assert len(client.get("/api/v1/budgets/", headers=h).json()) == 1


def test_persisting_the_same_date_twice_returns_normally_and_keeps_one_row(db):
    d = date(2026, 3, 15)
    rates = {"EUR": Decimal("1"), "USD": Decimal("1.10"), "GBP": Decimal("0.85")}

    rates_service._persist_rates(db, d, rates)
    # The concurrent loser: a second session that also missed the cache and fetched.
    other = Session(bind=db.get_bind())
    try:
        rates_service._persist_rates(other, d, {**rates, "USD": Decimal("1.11")})
    finally:
        other.close()

    rows = db.query(FxRate).filter(FxRate.rate_date == d).all()
    assert len(rows) == 3
    # The first writer's rate stands; the loser did not overwrite it.
    assert {r.currency: r.rate_vs_eur for r in rows}["USD"] == Decimal("1.10")
