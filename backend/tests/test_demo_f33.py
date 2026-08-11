"""F33 — public demo account: seed, one-click login, and scheduled reset.

The two things worth guarding here are the gate and the blast radius. The
demo-login endpoint hands a valid session to anyone who asks, so it must be
invisible unless DEMO_MODE is on; and reset_demo() deletes rows on a schedule
against a live deployment, so it must never touch a user that is not the demo
user.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.security import hash_password
from app.models.budget import Budget
from app.models.transaction import Category, Transaction, TransactionType
from app.models.user import User
from app.services.demo_seed import get_demo_user, reset_demo, seed_demo


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    yield


# ── the gate ──────────────────────────────────────────────────────────────

def test_demo_login_404s_when_demo_mode_off(client):
    """404, not 403 — a production deploy shouldn't reveal the route exists."""
    assert client.post("/api/v1/auth/demo-login").status_code == 404


def test_demo_login_returns_a_usable_token(client, demo_mode):
    r = client.post("/api/v1/auth/demo-login")
    assert r.status_code == 200
    token = r.json()["access_token"]
    assert token

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == settings.DEMO_USER_EMAIL


def test_demo_login_is_repeatable_without_duplicating_data(client, demo_mode, db):
    first = client.post("/api/v1/auth/demo-login")
    user = get_demo_user(db)
    count = db.query(Transaction).filter(Transaction.user_id == user.id).count()

    second = client.post("/api/v1/auth/demo-login")
    assert first.status_code == second.status_code == 200
    assert db.query(Transaction).filter(Transaction.user_id == user.id).count() == count


# ── seeded data quality (the §3 acceptance numbers) ───────────────────────

def test_seed_produces_a_populated_account(db):
    user = seed_demo(db)
    tx = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()

    assert len(tx) >= 60
    assert len({(t.transaction_date.year, t.transaction_date.month) for t in tx}) >= 3
    assert len({t.category for t in tx}) >= 5
    assert any(t.type == TransactionType.income for t in tx)
    assert any(t.type == TransactionType.expense for t in tx)
    assert len(budgets) >= 4


def test_seed_has_no_future_dated_transactions(db):
    user = seed_demo(db)
    tx = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    assert [t for t in tx if t.transaction_date > date.today()] == []


def test_budgets_show_both_over_and_under_spend(db):
    """The budgets page should demonstrate something, not read all-green."""
    user = seed_demo(db)
    today = date.today()
    spend: dict[str, Decimal] = {}
    for t in db.query(Transaction).filter(Transaction.user_id == user.id):
        if (t.type == TransactionType.expense
                and (t.transaction_date.year, t.transaction_date.month)
                == (today.year, today.month)):
            spend[t.category] = spend.get(t.category, Decimal(0)) + t.amount

    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    over = [b for b in budgets if spend.get(b.category, Decimal(0)) > b.limit_amount]
    under = [b for b in budgets if spend.get(b.category, Decimal(0)) < b.limit_amount]
    assert over, "no category is over budget"
    assert under, "no category is under budget"


def test_seed_is_deterministic(db):
    """Same data every reset — a screenshot or a second visit must match."""
    user = seed_demo(db)
    before = sorted(
        (t.description, str(t.amount), t.transaction_date.isoformat())
        for t in db.query(Transaction).filter(Transaction.user_id == user.id)
    )
    reset_demo(db)
    after = sorted(
        (t.description, str(t.amount), t.transaction_date.isoformat())
        for t in db.query(Transaction).filter(Transaction.user_id == user.id)
    )
    assert before == after


# ── blast radius ──────────────────────────────────────────────────────────

def test_reset_only_touches_the_demo_user(db):
    """The whole risk of this feature in one test."""
    other = User(email="real.person@example.com",
                 hashed_password=hash_password("pw"), full_name="Real Person")
    db.add(other)
    db.commit()
    db.refresh(other)
    db.add(Transaction(user_id=other.id, amount=Decimal("42.00"),
                       type=TransactionType.expense, category=Category.food,
                       description="Their data", transaction_date=date.today()))
    db.add(Budget(user_id=other.id, category="food", limit_amount=Decimal("100"),
                  month=date.today().month, year=date.today().year))
    db.commit()

    seed_demo(db)
    reset_demo(db)

    assert db.query(Transaction).filter(Transaction.user_id == other.id).count() == 1
    assert db.query(Budget).filter(Budget.user_id == other.id).count() == 1
    assert db.get(User, other.id) is not None


def test_reset_is_a_noop_without_a_demo_user(db):
    """A misconfigured deploy should do nothing, not raise in a job loop."""
    assert get_demo_user(db) is None
    assert reset_demo(db) is None
