"""F32-fu1 — service-layer tests for the recurring-tag review surface.

F32 applies the 'recurring' tag with no way to disagree with it. These cover
the review queue and the two decisions a user can make about a group.

The load-bearing case is `test_rejected_group_is_not_retagged_on_next_run`:
apply_recurring_tags re-runs after every import, so a reject that only stripped
the tag would silently come back and the whole review surface would be
pointless.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Category, Transaction, TransactionType
from app.services.recurring_service import (
    apply_recurring_tags,
    list_recurring_review,
    resolve_recurring_group,
)
from tests.factories import UserFactory, bind_session


@pytest.fixture(autouse=True)
def _bind(db):
    bind_session(db)


def _make_tx(user_id: int, description: str, amount: Decimal, tx_date: date, db) -> Transaction:
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


def _seed_monthly(db, user_id: int, name: str, amount: str = "12.99") -> None:
    """Three monthly charges — enough to trip every detector gate."""
    for month in (1, 2, 3):
        _make_tx(user_id, name, Decimal(amount), date(2024, month, 15), db)


def _tag_names(db, user_id: int) -> set[str]:
    txs = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    return {t.name for tx in txs for t in tx.tags}


class TestReviewQueue:
    def test_lists_auto_tagged_groups_with_totals(self, db):
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix")
        db.commit()
        apply_recurring_tags(user.id, db)

        groups = list_recurring_review(user.id, db)

        assert len(groups) == 1
        g = groups[0]
        assert g["merchant"] == "netflix"
        assert g["transaction_count"] == 3
        assert g["median_amount"] == 12.99
        assert g["total_amount"] == pytest.approx(38.97)
        assert g["first_seen"] == date(2024, 1, 15)
        assert g["last_seen"] == date(2024, 3, 15)
        assert len(g["transaction_ids"]) == 3

    def test_empty_when_nothing_was_auto_tagged(self, db):
        user = UserFactory()
        _make_tx(user.id, "One off purchase", Decimal("40.00"), date(2024, 1, 5), db)
        db.commit()
        apply_recurring_tags(user.id, db)

        assert list_recurring_review(user.id, db) == []

    def test_biggest_total_first(self, db):
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix", "12.99")
        _seed_monthly(db, user.id, "Gym Membership", "45.00")
        db.commit()
        apply_recurring_tags(user.id, db)

        merchants = [g["merchant"] for g in list_recurring_review(user.id, db)]
        assert merchants == ["gym membership", "netflix"]

    def test_one_users_groups_are_invisible_to_another(self, db):
        a, b = UserFactory(), UserFactory()
        _seed_monthly(db, a.id, "Netflix")
        db.commit()
        apply_recurring_tags(a.id, db)

        assert len(list_recurring_review(a.id, db)) == 1
        assert list_recurring_review(b.id, db) == []


class TestConfirm:
    def test_confirming_removes_the_group_from_the_queue(self, db):
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix")
        db.commit()
        apply_recurring_tags(user.id, db)

        res = resolve_recurring_group(user.id, "Netflix", "confirm", db)

        assert res["transactions_updated"] == 3
        assert list_recurring_review(user.id, db) == []

    def test_confirming_keeps_the_recurring_tag(self, db):
        # Confirm means "yes, this really is recurring" — the tag must stay.
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix")
        db.commit()
        apply_recurring_tags(user.id, db)
        resolve_recurring_group(user.id, "Netflix", "confirm", db)

        names = _tag_names(db, user.id)
        assert "recurring" in names
        assert "recurring-confirmed" in names

    def test_confirming_twice_is_idempotent(self, db):
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix")
        db.commit()
        apply_recurring_tags(user.id, db)

        resolve_recurring_group(user.id, "Netflix", "confirm", db)
        second = resolve_recurring_group(user.id, "Netflix", "confirm", db)
        assert second["transactions_updated"] == 0


class TestReject:
    def test_rejecting_strips_the_recurring_tag(self, db):
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix")
        db.commit()
        apply_recurring_tags(user.id, db)

        res = resolve_recurring_group(user.id, "Netflix", "reject", db)

        assert res["transactions_updated"] == 3
        assert "recurring" not in _tag_names(db, user.id)
        assert list_recurring_review(user.id, db) == []

    def test_rejected_group_is_not_retagged_on_next_run(self, db):
        # The whole point of the feature: apply_recurring_tags runs after every
        # import, so a rejection has to survive it.
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix")
        db.commit()
        apply_recurring_tags(user.id, db)
        resolve_recurring_group(user.id, "Netflix", "reject", db)

        result = apply_recurring_tags(user.id, db)

        assert result["recurring_groups"] == 0
        assert "recurring" not in _tag_names(db, user.id)
        assert list_recurring_review(user.id, db) == []

    def test_rejecting_clears_a_previous_confirmation(self, db):
        # The two markers must never both be present.
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix")
        db.commit()
        apply_recurring_tags(user.id, db)
        resolve_recurring_group(user.id, "Netflix", "confirm", db)
        resolve_recurring_group(user.id, "Netflix", "reject", db)

        names = _tag_names(db, user.id)
        assert "recurring-confirmed" not in names
        assert "recurring-rejected" in names

    def test_rejecting_one_group_leaves_others_alone(self, db):
        user = UserFactory()
        _seed_monthly(db, user.id, "Netflix", "12.99")
        _seed_monthly(db, user.id, "Gym Membership", "45.00")
        db.commit()
        apply_recurring_tags(user.id, db)

        resolve_recurring_group(user.id, "Netflix", "reject", db)

        remaining = [g["merchant"] for g in list_recurring_review(user.id, db)]
        assert remaining == ["gym membership"]


class TestGuards:
    def test_unknown_merchant_is_a_no_op_not_an_error(self, db):
        user = UserFactory()
        res = resolve_recurring_group(user.id, "Nothing Here", "confirm", db)
        assert res["transactions_updated"] == 0

    def test_invalid_action_raises(self, db):
        user = UserFactory()
        with pytest.raises(ValueError):
            resolve_recurring_group(user.id, "Netflix", "maybe", db)
