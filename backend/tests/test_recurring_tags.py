"""F32 — Service-layer tests for apply_recurring_tags.

Exercises the service directly (no HTTP layer) against a real SQLite session.

Heuristic thresholds under test (agreed 2026-06-22):
  - Minimum occurrences : >=3 transactions per merchant group
  - Amount tolerance    : each amount within +-10% of the group median
  - Cadence             : monthly (>=3 distinct months, day-of-month +-3 days)
                          OR weekly (median inter-arrival <= 10 days)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Category, Transaction, TransactionType
from app.services.recurring_service import apply_recurring_tags
from tests.factories import UserFactory, bind_session


@pytest.fixture(autouse=True)
def _bind(db):
    bind_session(db)


def _make_tx(user_id: int, description: str, amount: Decimal, tx_date: date, db) -> Transaction:
    """Insert a bare expense transaction and return the ORM object."""
    tx = Transaction(
        user_id=user_id,
        amount=amount,
        type=TransactionType.expense,
        category=Category.entertainment,
        description=description,
        transaction_date=tx_date,
    )
    db.add(tx)
    db.flush()
    return tx


class TestMonthlyRecurring:
    """3-month same-merchant ~same-amount series must get the 'recurring' tag."""

    def test_monthly_series_gets_tagged(self, db):
        user = UserFactory()
        # Three months, 15th of each month, same amount
        _make_tx(user.id, "Netflix", Decimal("12.99"), date(2024, 1, 15), db)
        _make_tx(user.id, "Netflix", Decimal("12.99"), date(2024, 2, 15), db)
        _make_tx(user.id, "Netflix", Decimal("13.49"), date(2024, 3, 15), db)
        db.commit()

        result = apply_recurring_tags(user.id, db)

        assert result["recurring_groups"] == 1
        assert result["tagged_transactions"] == 3

        txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
        tag_names = {t.name for tx in txs for t in tx.tags}
        assert "recurring" in tag_names
        assert all(any(t.name == "recurring" for t in tx.tags) for tx in txs)

    def test_one_off_transaction_not_tagged(self, db):
        user = UserFactory()
        # Only one transaction -- should not be flagged
        _make_tx(user.id, "Etsy payment", Decimal("35.00"), date(2024, 3, 10), db)
        db.commit()

        result = apply_recurring_tags(user.id, db)

        assert result["recurring_groups"] == 0
        assert result["tagged_transactions"] == 0

        tx = db.query(Transaction).filter(Transaction.user_id == user.id).first()
        assert tx.tags == []

    def test_two_occurrences_not_tagged(self, db):
        """Two occurrences is below the minimum-3 threshold."""
        user = UserFactory()
        _make_tx(user.id, "Spotify", Decimal("9.99"), date(2024, 1, 5), db)
        _make_tx(user.id, "Spotify", Decimal("9.99"), date(2024, 2, 5), db)
        db.commit()

        result = apply_recurring_tags(user.id, db)

        assert result["recurring_groups"] == 0

    def test_amount_outlier_excluded(self, db):
        """A merchant group where one amount is >10% off median is not tagged."""
        user = UserFactory()
        _make_tx(user.id, "SomeService", Decimal("10.00"), date(2024, 1, 10), db)
        _make_tx(user.id, "SomeService", Decimal("10.00"), date(2024, 2, 10), db)
        _make_tx(user.id, "SomeService", Decimal("20.00"), date(2024, 3, 10), db)  # outlier
        db.commit()

        result = apply_recurring_tags(user.id, db)

        assert result["recurring_groups"] == 0


class TestIdempotency:
    """Re-running the pass must not duplicate tags or Tag rows."""

    def test_rerun_does_not_duplicate_tag(self, db):
        user = UserFactory()
        _make_tx(user.id, "Adobe", Decimal("54.99"), date(2024, 1, 20), db)
        _make_tx(user.id, "Adobe", Decimal("54.99"), date(2024, 2, 20), db)
        _make_tx(user.id, "Adobe", Decimal("54.99"), date(2024, 3, 20), db)
        db.commit()

        apply_recurring_tags(user.id, db)
        result2 = apply_recurring_tags(user.id, db)

        # Second run: tag already on all tx, so tagged_transactions == 0
        assert result2["tagged_transactions"] == 0

        # Each transaction must carry exactly one 'recurring' tag (no duplicates)
        txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
        for tx in txs:
            recurring_tags = [t for t in tx.tags if t.name == "recurring"]
            assert len(recurring_tags) == 1

    def test_tag_row_not_duplicated(self, db):
        """find-or-create must never produce two Tag rows with the same name."""
        from app.models.tag import Tag

        user = UserFactory()
        _make_tx(user.id, "Dropbox", Decimal("9.99"), date(2024, 1, 3), db)
        _make_tx(user.id, "Dropbox", Decimal("9.99"), date(2024, 2, 3), db)
        _make_tx(user.id, "Dropbox", Decimal("9.99"), date(2024, 3, 3), db)
        db.commit()

        apply_recurring_tags(user.id, db)
        apply_recurring_tags(user.id, db)

        tag_count = (
            db.query(Tag)
            .filter(Tag.user_id == user.id, Tag.name == "recurring")
            .count()
        )
        assert tag_count == 1


class TestUserIsolation:
    """A pass for user A must never touch user B's transactions."""

    def test_user_isolation(self, db):
        alice = UserFactory()
        bob = UserFactory()

        # Both users have an identical recurring series
        for month in (1, 2, 3):
            _make_tx(alice.id, "PrimeVideo", Decimal("8.99"), date(2024, month, 1), db)
            _make_tx(bob.id, "PrimeVideo", Decimal("8.99"), date(2024, month, 1), db)
        db.commit()

        # Run only for Alice
        apply_recurring_tags(alice.id, db)

        alice_txs = db.query(Transaction).filter(Transaction.user_id == alice.id).all()
        bob_txs = db.query(Transaction).filter(Transaction.user_id == bob.id).all()

        # Alice's transactions are tagged
        assert all(any(t.name == "recurring" for t in tx.tags) for tx in alice_txs)
        # Bob's transactions are untouched
        assert all(tx.tags == [] for tx in bob_txs)


class TestWeeklyCadence:
    """Weekly subscriptions (inter-arrival ~7 days) must also be detected."""

    def test_weekly_series_gets_tagged(self, db):
        user = UserFactory()
        # Four weekly transactions (every 7 days)
        _make_tx(user.id, "GymClass", Decimal("15.00"), date(2024, 3, 1), db)
        _make_tx(user.id, "GymClass", Decimal("15.00"), date(2024, 3, 8), db)
        _make_tx(user.id, "GymClass", Decimal("15.00"), date(2024, 3, 15), db)
        db.commit()

        result = apply_recurring_tags(user.id, db)

        assert result["recurring_groups"] == 1
        assert result["tagged_transactions"] == 3


class TestTagFilterable:
    """Tagged-recurring transactions must be retrievable via GET /transactions/?tag=recurring."""

    def test_tagged_txs_visible_via_tag_filter(self, client):
        # Register + login (use .dev domain — .test is IANA-reserved and rejected by EmailStr)
        client.post("/api/v1/auth/register", json={
            "email": "rec@finly.dev", "password": "pass123", "full_name": "Rec User"
        })
        res = client.post("/api/v1/auth/login", data={"username": "rec@finly.dev", "password": "pass123"})
        headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

        # Create 3 monthly transactions via the API
        for month in (1, 2, 3):
            client.post("/api/v1/transactions/", json={
                "amount": "9.99",
                "type": "expense",
                "category": "entertainment",
                "description": "Spotify Monthly",
                "transaction_date": f"2024-{month:02d}-15",
            }, headers=headers)

        # Run the detection endpoint
        tag_res = client.post("/api/v1/transactions/detect-recurring", headers=headers)
        assert tag_res.status_code == 200
        body = tag_res.json()
        assert body["recurring_groups"] >= 1

        # Filter by tag
        filter_res = client.get("/api/v1/transactions/?tag=recurring", headers=headers)
        assert filter_res.status_code == 200
        tagged = filter_res.json()
        assert len(tagged) == 3
        for tx in tagged:
            tag_names = [t["name"] for t in tx["tags"]]
            assert "recurring" in tag_names
