"""Typed factory-boy factories for deterministic test fixtures.

Each factory writes through the active SQLAlchemy session stored on the class
via `_set_session`, so tests don't leak global state. Prefer these over
hand-rolled dicts — they keep tests declarative and refactor-safe.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import factory
from factory.alchemy import SQLAlchemyModelFactory

from app.models.budget import Budget
from app.models.transaction import Category, Transaction, TransactionType
from app.models.user import User
from app.core.security import hash_password

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class _Base(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session_persistence = "commit"


class UserFactory(_Base):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@finly.test")
    full_name = factory.Faker("name")
    hashed_password = factory.LazyFunction(lambda: hash_password("pass123"))
    is_active = True


class BudgetFactory(_Base):
    class Meta:
        model = Budget

    owner = factory.SubFactory(UserFactory)
    user_id = factory.SelfAttribute("owner.id")
    category = "food"
    limit_amount = Decimal("300.00")
    month = 6
    year = 2024


class TransactionFactory(_Base):
    class Meta:
        model = Transaction

    owner = factory.SubFactory(UserFactory)
    user_id = factory.SelfAttribute("owner.id")
    amount = Decimal("25.00")
    type = TransactionType.expense
    category = Category.food
    description = factory.Faker("sentence", nb_words=3)
    transaction_date = date(2024, 6, 15)


def bind_session(session: "Session") -> None:
    """Point every factory at the given session. Call once per test."""
    for factory_cls in (UserFactory, BudgetFactory, TransactionFactory):
        factory_cls._meta.sqlalchemy_session = session
