"""F39 — the Budgets bar and the overspend alert must measure spend the same way.

They used to disagree: the bar summed coalesce(base_amount, amount) and excluded split
parents; the alert summed the raw un-converted amount and double-counted split parents.
On a mixed-currency or split expense they diverged by a factor the user could see. Both
now go through category_spend(); these tests pin that they agree, and — via the negative
control at the bottom of the file's intent — that agreement is real.
"""
from decimal import Decimal

from app.models.transaction import Category, Transaction, TransactionType
from app.services.transactions import category_spend, get_monthly_summary
from app.services.budget_alert_service import check_budget_overspend
from tests.factories import BudgetFactory, TransactionFactory, UserFactory, bind_session

MONTH, YEAR = 6, 2024


def _summary_expense(summary, category="food"):
    for c in summary["categories"]:
        if c["category"] == category:
            return c["expenses"]
    return Decimal("0")


def _mk(db, user, **kw):
    kw.setdefault("category", Category.food)
    kw.setdefault("type", TransactionType.expense)
    return TransactionFactory(owner=user, **kw)


def _scenarios(db, user):
    """5 fixed scenarios, each a list of (amount, base_amount) expense rows plus optional
    split structure, and the expected base-currency spend."""
    return {
        "mixed currency (120 USD = 60 EUR base)": (
            [dict(amount=Decimal("120.00"), base_amount=Decimal("60.00"))],
            Decimal("60.00"),
        ),
        "split 2x30 (parent excluded)": (
            "split",
            Decimal("60.00"),
        ),
        "same-currency simple": (
            [dict(amount=Decimal("45.00"), base_amount=Decimal("45.00"))],
            Decimal("45.00"),
        ),
        "no base_amount (falls back to amount)": (
            [dict(amount=Decimal("30.00"), base_amount=None)],
            Decimal("30.00"),
        ),
        "several rows": (
            [dict(amount=Decimal("10.00"), base_amount=Decimal("10.00")),
             dict(amount=Decimal("20.00"), base_amount=Decimal("20.00")),
             dict(amount=Decimal("120.00"), base_amount=Decimal("60.00"))],
            Decimal("90.00"),
        ),
    }


def _apply(db, user, spec):
    if spec == "split":
        parent = _mk(db, user, amount=Decimal("60.00"), base_amount=Decimal("60.00"))
        db.flush()
        for _ in range(2):
            c = _mk(db, user, amount=Decimal("30.00"), base_amount=Decimal("30.00"))
            c.parent_transaction_id = parent.id
        db.flush()
    else:
        for row in spec:
            _mk(db, user, **row)
        db.flush()


def test_bar_and_alert_agree_across_five_scenarios(db):
    for name, (spec, expected) in _scenarios(db, None).items():
        bind_session(db)
        user = UserFactory()
        db.flush()
        _apply(db, user, spec)

        spent = category_spend(user.id, Category.food, MONTH, YEAR, db)
        summary = get_monthly_summary(user.id, MONTH, YEAR, db)
        bar = _summary_expense(summary)

        assert spent == expected, f"{name}: category_spend {spent} != expected {expected}"
        assert bar == expected, f"{name}: summary bar {bar} != expected {expected}"
        assert spent == bar, f"{name}: alert {spent} != bar {bar}"
        # clean the slate for the next scenario
        db.query(Transaction).delete()
        db.flush()


def test_scenario_A_mixed_currency_under_budget_no_alert(db):
    bind_session(db)
    user = UserFactory()
    db.flush()
    BudgetFactory(owner=user, category="food", limit_amount=Decimal("100.00"),
                  month=MONTH, year=YEAR)
    _mk(db, user, amount=Decimal("120.00"), base_amount=Decimal("60.00"))
    db.flush()

    assert check_budget_overspend(user.id, Category.food, MONTH, YEAR, db) is None
    summary = get_monthly_summary(user.id, MONTH, YEAR, db)
    assert _summary_expense(summary) == Decimal("60.00")
    food = next(c for c in summary["categories"] if c["category"] == "food")
    assert food["budget_remaining"] == Decimal("40.00")


def test_scenario_B_split_under_budget_no_alert(db):
    bind_session(db)
    user = UserFactory()
    db.flush()
    BudgetFactory(owner=user, category="food", limit_amount=Decimal("100.00"),
                  month=MONTH, year=YEAR)
    _apply(db, user, "split")

    assert check_budget_overspend(user.id, Category.food, MONTH, YEAR, db) is None
    summary = get_monthly_summary(user.id, MONTH, YEAR, db)
    assert _summary_expense(summary) == Decimal("60.00")


def test_boundary_exactly_at_limit_does_not_alert_one_cent_over_does(db):
    bind_session(db)
    user = UserFactory()
    db.flush()
    BudgetFactory(owner=user, category="food", limit_amount=Decimal("100.00"),
                  month=MONTH, year=YEAR)
    # exactly at the limit — must NOT alert
    _mk(db, user, amount=Decimal("100.00"), base_amount=Decimal("100.00"))
    db.flush()
    assert check_budget_overspend(user.id, Category.food, MONTH, YEAR, db) is None

    # one cent over — must alert
    _mk(db, user, amount=Decimal("0.01"), base_amount=Decimal("0.01"))
    db.flush()
    alert = check_budget_overspend(user.id, Category.food, MONTH, YEAR, db)
    assert alert is not None
    assert alert["event"] == "budget_alert"
    assert alert["spent"] == "100.01"


def test_no_budget_for_category_returns_none(db):
    bind_session(db)
    user = UserFactory()
    db.flush()
    # spend exists but there is NO budget row for this category/month
    _mk(db, user, amount=Decimal("500.00"), base_amount=Decimal("500.00"))
    db.flush()
    assert check_budget_overspend(user.id, Category.food, MONTH, YEAR, db) is None
