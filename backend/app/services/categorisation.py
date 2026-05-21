"""
Category auto-assign rules (F11) — user-defined rules that map transaction
descriptions to categories. Rules match in priority order (lowest number wins;
ties broken by creation date).
"""
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.categorisation_rule import CategorisationRule, MatchType
from app.models.transaction import Category, Transaction, TransactionType


@dataclass
class RuleMatch:
    category: Category
    rule_id: int


def _compile(pattern: str) -> re.Pattern | None:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None


def _rule_matches(rule: CategorisationRule, description: str) -> bool:
    """Case-insensitive match of a single rule against a description."""
    if not rule.enabled:
        return False
    desc = description or ""
    value = rule.match_value or ""
    if rule.match_type == MatchType.contains or rule.match_type == "contains":
        return value.lower() in desc.lower()
    if rule.match_type == MatchType.equals or rule.match_type == "equals":
        return desc.strip().lower() == value.strip().lower()
    if rule.match_type == MatchType.starts_with or rule.match_type == "starts_with":
        return desc.lower().startswith(value.lower())
    if rule.match_type == MatchType.regex or rule.match_type == "regex":
        compiled = _compile(value)
        return bool(compiled and compiled.search(desc))
    return False


def match_description(description: str, user_id: int, db: Session) -> RuleMatch | None:
    """Return the first matching rule for the given description, or None."""
    rules = (
        db.query(CategorisationRule)
        .filter(CategorisationRule.user_id == user_id, CategorisationRule.enabled.is_(True))
        .order_by(CategorisationRule.priority.asc(), CategorisationRule.created_at.asc())
        .all()
    )
    for rule in rules:
        if _rule_matches(rule, description):
            return RuleMatch(
                category=rule.category if isinstance(rule.category, Category) else Category(rule.category),
                rule_id=rule.id,
            )
    return None


def recategorise_uncategorised(user_id: int, db: Session) -> int:
    """
    Apply user rules to every transaction currently on `Category.other` and
    update those where a rule matches. Returns how many were updated.
    Income transactions (Category.salary / freelance) are left alone.
    """
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.category == Category.other,
            Transaction.type == TransactionType.expense,
        )
        .all()
    )
    updated = 0
    for tx in txs:
        match = match_description(tx.description, user_id, db)
        if match is not None:
            tx.category = match.category
            tx.categorised_by_rule_id = match.rule_id
            updated += 1
    if updated:
        db.commit()
    return updated
