"""Service-layer integration tests for budgets.

Exercises the service directly (no HTTP layer) against a real SQLite session
so we cover branches that the endpoint tests don't — duplicate handling,
ordering, per-user isolation, month/year filtering edge cases.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.schemas.budget import BudgetCreate
from app.services.budgets import create_budget, delete_budget, get_user_budgets
from tests.factories import BudgetFactory, UserFactory, bind_session


@pytest.fixture(autouse=True)
def _bind(db):
    bind_session(db)


def _make_budget_in(**overrides) -> BudgetCreate:
    payload = {
        "category": "food",
        "limit_amount": Decimal("300.00"),
        "month": 6,
        "year": 2024,
    }
    payload.update(overrides)
    return BudgetCreate(**payload)


class TestCreateBudget:
    def test_persists_with_user_scope(self, db):
        user = UserFactory()
        budget = create_budget(_make_budget_in(), user.id, db)

        assert budget.id is not None
        assert budget.user_id == user.id
        assert budget.limit_amount == Decimal("300.00")

    def test_duplicate_same_user_raises_409(self, db):
        user = UserFactory()
        create_budget(_make_budget_in(), user.id, db)

        with pytest.raises(HTTPException) as exc:
            create_budget(_make_budget_in(), user.id, db)

        assert exc.value.status_code == 409

    def test_same_category_month_allowed_for_different_user(self, db):
        alice, bob = UserFactory(), UserFactory()
        create_budget(_make_budget_in(), alice.id, db)

        # Should not raise — budgets are scoped per user
        create_budget(_make_budget_in(), bob.id, db)

        assert len(get_user_budgets(alice.id, db)) == 1
        assert len(get_user_budgets(bob.id, db)) == 1

    def test_same_category_different_month_allowed(self, db):
        user = UserFactory()
        create_budget(_make_budget_in(month=6), user.id, db)
        create_budget(_make_budget_in(month=7), user.id, db)

        assert len(get_user_budgets(user.id, db)) == 2


class TestListBudgets:
    def test_returns_only_current_user_budgets(self, db):
        alice, bob = UserFactory(), UserFactory()
        BudgetFactory.create_batch(3, owner=alice, user_id=alice.id)
        BudgetFactory(owner=bob, user_id=bob.id, month=1)

        result = get_user_budgets(alice.id, db)

        assert len(result) == 3
        assert all(b.user_id == alice.id for b in result)

    def test_ordered_newest_first(self, db):
        user = UserFactory()
        BudgetFactory(owner=user, user_id=user.id, year=2023, month=12)
        BudgetFactory(owner=user, user_id=user.id, year=2024, month=1)
        BudgetFactory(owner=user, user_id=user.id, year=2024, month=6)

        result = get_user_budgets(user.id, db)

        assert [(b.year, b.month) for b in result] == [(2024, 6), (2024, 1), (2023, 12)]

    @pytest.mark.parametrize(
        "filter_kwargs,expected_count",
        [
            ({"month": 6, "year": 2024}, 1),
            ({"month": 6}, 2),  # June across any year
            ({"year": 2024}, 2),  # any month in 2024
            ({}, 3),  # no filter
            ({"month": 12, "year": 2099}, 0),
        ],
    )
    def test_filter_matrix(self, db, filter_kwargs, expected_count):
        user = UserFactory()
        BudgetFactory(owner=user, user_id=user.id, month=6, year=2024)
        BudgetFactory(owner=user, user_id=user.id, month=6, year=2023, category="transport")
        BudgetFactory(owner=user, user_id=user.id, month=1, year=2024, category="health")

        result = get_user_budgets(user.id, db, **filter_kwargs)

        assert len(result) == expected_count


class TestDeleteBudget:
    def test_removes_own_budget(self, db):
        user = UserFactory()
        budget = BudgetFactory(owner=user, user_id=user.id)

        delete_budget(budget.id, user.id, db)

        assert get_user_budgets(user.id, db) == []

    def test_cannot_delete_other_users_budget(self, db):
        alice, bob = UserFactory(), UserFactory()
        alice_budget = BudgetFactory(owner=alice, user_id=alice.id)

        with pytest.raises(HTTPException) as exc:
            delete_budget(alice_budget.id, bob.id, db)

        assert exc.value.status_code == 404
        # And Alice's budget is still there
        assert len(get_user_budgets(alice.id, db)) == 1

    def test_missing_id_raises_404(self, db):
        user = UserFactory()

        with pytest.raises(HTTPException) as exc:
            delete_budget(9999, user.id, db)

        assert exc.value.status_code == 404
