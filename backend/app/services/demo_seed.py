"""F33 — seed and reset the public demo account.

A recruiter following the GitHub link should land in a working app, not an
empty state. This builds one demo user with four months of realistic
transactions, budgets that are deliberately a mix of over and under, and a
savings goal, so every page has something to show.

The demo account stays **editable** — a read-only demo feels fake. What keeps
it from being trashed is :func:`reset_demo`, run on a schedule from
``main.py``.

⚠️ Every destructive path here is scoped to the single user whose email is
``settings.DEMO_USER_EMAIL``, and the caller is gated on ``DEMO_MODE``. There
is deliberately no "wipe all users" branch: this code runs on a live deploy,
and a global delete guarded only by a config flag is one typo away from an
incident.
"""
from __future__ import annotations

import logging
import random
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.budget import Budget
from app.models.transaction import Category, Transaction, TransactionType
from app.models.user import User

logger = logging.getLogger(__name__)

# Fixed seed → the same demo data every reset. A recruiter comparing two visits
# (or a screenshot in the README) should not see different numbers.
_RNG_SEED = 20260811

# (description, category, min, max) for expenses
_EXPENSE_PATTERNS = [
    ("Rent", Category.housing, 1150, 1150),
    ("Electricity & gas", Category.housing, 68, 124),
    ("Home insurance", Category.housing, 21, 21),
    ("Weekly shop", Category.food, 48, 96),
    ("Bakery", Category.food, 4, 12),
    ("Coffee", Category.food, 3, 6),
    ("Lunch out", Category.food, 9, 22),
    ("Train season ticket", Category.transport, 92, 92),
    ("Fuel", Category.transport, 44, 78),
    ("Bike service", Category.transport, 25, 60),
    ("Cinema", Category.entertainment, 11, 26),
    ("Streaming subscription", Category.entertainment, 8, 16),
    ("Concert tickets", Category.entertainment, 35, 85),
    ("Pharmacy", Category.health, 7, 34),
    ("Gym membership", Category.health, 29, 29),
    ("Dentist", Category.health, 45, 130),
    ("Clothing", Category.shopping, 25, 110),
    ("Electronics", Category.shopping, 30, 180),
    ("Books", Category.shopping, 12, 38),
    ("Charity donation", Category.other, 10, 25),
]

_INCOME_PATTERNS = [
    ("Monthly salary", Category.salary, 3200, 3200),
    ("Freelance invoice", Category.freelance, 350, 1100),
]

# limit_amount per category for the current month — chosen so at least one
# lands over budget and at least one comfortably under (an acceptance
# criterion, and it makes the budgets page actually demonstrate something).
_BUDGET_LIMITS = {
    Category.housing: Decimal("1400.00"),
    Category.food: Decimal("400.00"),
    Category.transport: Decimal("250.00"),
    Category.entertainment: Decimal("90.00"),    # deliberately tight → over
    Category.health: Decimal("150.00"),
    Category.shopping: Decimal("400.00"),
}


def _month_starts(n: int, today: date) -> list[date]:
    """The first day of each of the last ``n`` months, oldest first."""
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _days_in_month(d: date) -> int:
    if d.month == 12:
        return 31
    return (date(d.year, d.month + 1, 1) - d).days


def get_demo_user(db: Session) -> User | None:
    return db.query(User).filter(User.email == settings.DEMO_USER_EMAIL).first()


def _build_transactions(user_id: int, today: date) -> list[Transaction]:
    rng = random.Random(_RNG_SEED)
    rows: list[Transaction] = []

    for start in _month_starts(4, today):
        span = _days_in_month(start)
        # Cap the current (partial) month at today, so the demo never shows
        # transactions dated in the future.
        last_day = today.day if (start.year, start.month) == (today.year, today.month) else span

        for desc, cat, lo, hi in _INCOME_PATTERNS:
            if cat is Category.freelance and rng.random() < 0.35:
                continue          # freelance work is lumpy, not every month
            day = min(25 if cat is Category.salary else rng.randint(5, 26), last_day)
            if day < 1:
                continue
            rows.append(Transaction(
                user_id=user_id,
                amount=Decimal(rng.randint(lo, hi)).quantize(Decimal("0.01")),
                type=TransactionType.income,
                category=cat,
                description=desc,
                transaction_date=date(start.year, start.month, day),
                currency="EUR",
            ))

        for desc, cat, lo, hi in _EXPENSE_PATTERNS:
            # Frequent small things recur within the month; big ones don't.
            times = 4 if lo < 15 else (2 if lo < 50 else 1)
            for _ in range(times):
                day = rng.randint(1, last_day) if last_day >= 1 else 1
                if last_day < 1:
                    continue
                rows.append(Transaction(
                    user_id=user_id,
                    amount=Decimal(rng.randint(lo, hi)).quantize(Decimal("0.01")),
                    type=TransactionType.expense,
                    category=cat,
                    description=desc,
                    transaction_date=date(start.year, start.month, day),
                    currency="EUR",
                ))
    return rows


def _build_budgets(user_id: int, today: date) -> list[Budget]:
    return [
        Budget(user_id=user_id, category=cat.value, limit_amount=limit,
               month=today.month, year=today.year)
        for cat, limit in _BUDGET_LIMITS.items()
    ]


def seed_demo(db: Session, *, force: bool = False) -> User:
    """Create the demo user and its data. Idempotent unless ``force``.

    Returns the demo user either way, so callers can mint a token against it.
    """
    user = get_demo_user(db)
    if user and not force:
        if db.query(Transaction).filter(Transaction.user_id == user.id).count():
            return user                      # already seeded, nothing to do

    if not user:
        user = User(
            email=settings.DEMO_USER_EMAIL,
            hashed_password=hash_password(settings.DEMO_USER_PASSWORD),
            full_name=settings.DEMO_USER_NAME,
            base_currency="EUR",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    today = date.today()
    db.add_all(_build_transactions(user.id, today))
    db.add_all(_build_budgets(user.id, today))
    db.commit()
    db.refresh(user)
    logger.info("F33: demo account seeded (user_id=%s)", user.id)
    return user


def reset_demo(db: Session) -> User | None:
    """Wipe **only the demo user's** rows and reseed.

    Returns None when there is no demo user, so a misconfigured deploy is a
    no-op rather than an error loop.
    """
    user = get_demo_user(db)
    if not user:
        logger.info("F33: reset skipped — no demo user")
        return None

    # Explicitly scoped to user.id. Do not widen these filters.
    #
    # synchronize_session="fetch" matters here. With False, the deleted rows
    # stay in the session's identity map; SQLite then reissues the same
    # primary keys to the reseed and SQLAlchemy warns it is replacing a live
    # identity — a stale-object hazard. "fetch" evicts exactly the rows that
    # were deleted. (expunge_all() also silences the warning, but it detaches
    # the *caller's* objects too, which raises DetachedInstanceError on
    # anything they were still holding.)
    db.query(Transaction).filter(Transaction.user_id == user.id).delete(
        synchronize_session="fetch")
    db.query(Budget).filter(Budget.user_id == user.id).delete(
        synchronize_session="fetch")
    db.commit()

    seed_demo(db, force=True)
    logger.info("F33: demo account reset (user_id=%s)", user.id)
    return user
