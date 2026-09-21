"""F44 — query budgets, asserted: the list is not N+1, the year report is not 12x, rate lookups are
per DATE not per row, and the split-parent subquery is scoped to the caller."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.fx_rate import FxRate
from app.models.tag import Tag
from app.models.transaction import Category, Transaction, TransactionType
from app.models.user import User
from app.services import report_service
from app.services.transactions import _excluding_split_parents, get_monthly_summary, plan_base_amounts
from tests.query_counter import assert_max_queries, count_queries


def _user(client, db, email="f44@finly.dev"):
    client.post("/api/v1/auth/register", json={"email": email, "password": "pass12345", "full_name": "F44"})
    r = client.post("/api/v1/auth/login", data={"username": email, "password": "pass12345"})
    uid = db.query(User.id).filter(User.email == email).scalar()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, uid


def _tx(uid, amount, day, ttype=TransactionType.expense, cat=Category.food, currency="EUR", parent=None):
    return Transaction(user_id=uid, amount=Decimal(amount), type=ttype, category=cat, description="x",
                       transaction_date=day, currency=currency, base_amount=Decimal(amount),
                       parent_transaction_id=parent)


def test_listing_100_tagged_transactions_is_not_n_plus_one(client, db):
    h, uid = _user(client, db)
    tag = Tag(user_id=uid, name="groceries"); db.add(tag); db.flush()
    for i in range(100):
        t = _tx(uid, "10.00", date(2026, 3, 1) + timedelta(days=i % 28)); t.tags.append(tag); db.add(t)
    db.commit()
    with assert_max_queries(db.get_bind(), 3):  # user lookup + rows + one selectin for tags (was 102)
        r = client.get("/api/v1/transactions/?limit=100", headers=h)
    assert r.status_code == 200 and len(r.json()) == 100
    assert all(t["tags"] == [{"id": tag.id, "name": "groceries"}] for t in r.json())


def test_year_totals_are_one_query_and_equal_the_sum_of_the_twelve_months(client, db):
    _, uid = _user(client, db)
    rows = [_tx(uid, "100.00", date(2026, m, 5)) for m in range(1, 13)]
    rows += [_tx(uid, "1500.00", date(2026, m, 25), ttype=TransactionType.income, cat=Category.salary) for m in (1, 6, 12)]
    rows += [_tx(uid, "33.33", date(2026, 7, 9), cat=Category.transport), _tx(uid, "999.00", date(2025, 12, 31))]
    db.add_all(rows); db.flush()
    parent = _tx(uid, "80.00", date(2026, 4, 2), cat=Category.shopping); db.add(parent); db.flush()
    db.add_all([_tx(uid, "50.00", date(2026, 4, 2), cat=Category.shopping, parent=parent.id),
                _tx(uid, "30.00", date(2026, 4, 2), cat=Category.entertainment, parent=parent.id)])
    db.commit()

    with assert_max_queries(db.get_bind(), 4):  # was 25
        got = report_service._year_totals(uid, 2026, db)

    months = [get_monthly_summary(uid, m, 2026, db) for m in range(1, 13)]  # the old definition
    inc = sum((Decimal(m["total_income"]) for m in months), Decimal("0"))
    exp = sum((Decimal(m["total_expenses"]) for m in months), Decimal("0"))
    cats: dict[str, Decimal] = {}
    for m in months:
        for c in m["categories"]:
            cats[c["category"]] = cats.get(c["category"], Decimal("0")) + Decimal(c["expenses"])
    assert (got["income"], got["expenses"], got["net"]) == (inc, exp, inc - exp)
    assert dict(got["by_category"]) == {k: v for k, v in cats.items() if v > 0}
    assert got["expenses"] == Decimal("1313.33")  # 12x100 + 33.33 + the split children (50+30), parent excluded, 2025 excluded


def test_a_base_currency_plan_looks_rates_up_once_per_date(client, db):
    _, uid = _user(client, db)
    days = [date(2026, 2, 1) + timedelta(days=i) for i in range(30)]
    for d in days:
        db.add_all([FxRate(rate_date=d, currency="EUR", rate_vs_eur=Decimal("1")),
                    FxRate(rate_date=d, currency="USD", rate_vs_eur=Decimal("1.10"))])
    db.add_all([_tx(uid, "10.00", days[i % 30], currency="USD") for i in range(500)])
    db.commit()
    with count_queries(db.get_bind()) as seen:
        planned = plan_base_amounts(uid, "EUR", db)
    assert len(planned) == 500 and all(v is not None for _, v in planned)
    assert len(seen) <= 32, f"{len(seen)} statements for 500 rows over 30 dates"


def test_the_split_parent_subquery_is_scoped_to_the_user(db):
    q = _excluding_split_parents(db.query(Transaction.id), 42)
    sql = str(q.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "parent_transaction_id IS NOT NULL" in sql and "user_id = 42" in sql
    unscoped = str(_excluding_split_parents(db.query(Transaction.id)).statement.compile(compile_kwargs={"literal_binds": True}))
    assert "user_id" not in unscoped  # control: without a user it stays the old global subquery
