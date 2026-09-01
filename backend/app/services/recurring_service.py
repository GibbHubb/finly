"""Detect recurring (subscription-like) transactions from spending history.

F32 — apply_recurring_tags
--------------------------
Heuristic thresholds (agreed 2026-06-22):
  - Minimum occurrences : ≥3 distinct transactions per merchant group
  - Amount tolerance    : each transaction must be within ±10 % of the group
                          median amount
  - Cadence             : monthly (day-of-month within ±3 days across ≥3
                          distinct calendar months) OR weekly (median inter-
                          arrival interval ≤ 10 days with ≥3 occurrences)

Description grouping reuses the existing _normalise() helper — no second
description-matching engine is introduced.  The F29 find-or-create helper
(app.services.tags.resolve_tag) handles tag persistence so no new tag-
assignment code path is added.
"""
import logging
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

from sqlalchemy.orm import Session

from app.models.transaction import Transaction

log = logging.getLogger(__name__)

# Generic noise words that would match too many unrelated transactions
_NOISE = {"pin", "betaling", "ideal", "af", "bij", "naar", "van", "te", "de"}
_MIN_MERCHANT_LEN = 5


def _normalise(description: str) -> str:
    """Lowercase, strip non-alphanumeric, collapse whitespace."""
    text = re.sub(r"[^a-z0-9 ]", "", description.lower()).strip()
    return re.sub(r"\s+", " ", text)


def detect(user_id: int, db: Session) -> list[dict]:
    """Return a list of detected recurring charges for *user_id*.

    A merchant is flagged recurring if it appears as an expense in ≥2
    distinct calendar months with the day-of-month within ±3 days across
    appearances.
    """
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == "expense",
        )
        .order_by(Transaction.transaction_date.asc())
        .all()
    )

    # Group by normalised merchant name
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for tx in rows:
        key = _normalise(tx.description)
        if len(key) < _MIN_MERCHANT_LEN:
            continue
        if key in _NOISE:
            continue
        groups[key].append(tx)

    results: list[dict] = []
    for merchant, txs in groups.items():
        # Collect distinct (year-month, day) pairs
        month_days: dict[str, int] = {}
        for tx in txs:
            ym = f"{tx.transaction_date.year}-{tx.transaction_date.month:02d}"
            # Keep first occurrence per month
            if ym not in month_days:
                month_days[ym] = tx.transaction_date.day

        if len(month_days) < 2:
            continue

        # Check ±3-day window: median day, then all must be within ±3
        days = list(month_days.values())
        med_day = int(median(days))
        if not all(abs(d - med_day) <= 3 for d in days):
            continue

        amounts = [float(tx.amount) for tx in txs]
        monthly_amount = round(sum(amounts) / len(month_days), 2)
        last_tx = txs[-1]

        results.append({
            "merchant": merchant,
            "monthly_amount": monthly_amount,
            "typical_day": med_day,
            "months_detected": len(month_days),
            "last_seen": str(last_tx.transaction_date),
        })

    # Sort by monthly_amount descending (biggest subscriptions first)
    results.sort(key=lambda r: r["monthly_amount"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# F32 — Auto-tag recurring transactions
# ---------------------------------------------------------------------------

_MIN_OCCURRENCES = 3          # at least this many transactions in the group
_AMOUNT_TOLERANCE = 0.10      # ±10 % of group median amount
_WEEKLY_MAX_INTERVAL_DAYS = 10  # median inter-arrival ≤ this → weekly cadence
_MONTHLY_DAY_WINDOW = 3       # ±3 days on day-of-month for monthly cadence
_TAG_NAME = "recurring"

# F32-fu1 — marks a group the user has explicitly accepted, so it drops out of
# the review queue permanently. Deliberately a second *tag* rather than a new
# column: it reuses resolve_tag + the existing M2M, needs no migration, and the
# user can see and undo it through the normal tag UI like any other tag.
_CONFIRMED_TAG_NAME = "recurring-confirmed"

# F32-fu1 — records that the user disagreed with the detector for this group.
# This has to persist: apply_recurring_tags re-runs after every import, so a
# reject that only removed the tag would silently come back next time and the
# review UI would be pointless. Groups carrying this tag are skipped entirely.
_REJECTED_TAG_NAME = "recurring-rejected"


def _is_monthly(txs: list[Transaction]) -> bool:
    """True if ≥3 distinct calendar months with day-of-month within ±3 days."""
    month_days: dict[str, int] = {}
    for tx in txs:
        ym = f"{tx.transaction_date.year}-{tx.transaction_date.month:02d}"
        if ym not in month_days:
            month_days[ym] = tx.transaction_date.day
    if len(month_days) < _MIN_OCCURRENCES:
        return False
    days = list(month_days.values())
    med = int(median(days))
    return all(abs(d - med) <= _MONTHLY_DAY_WINDOW for d in days)


def _is_weekly(txs: list[Transaction]) -> bool:
    """True if ≥3 occurrences with median inter-arrival interval ≤ 10 days."""
    if len(txs) < _MIN_OCCURRENCES:
        return False
    dates = sorted(tx.transaction_date for tx in txs)
    intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    if not intervals:
        return False
    return int(median(intervals)) <= _WEEKLY_MAX_INTERVAL_DAYS


def _within_amount_tolerance(txs: list[Transaction]) -> bool:
    """True if every transaction amount is within ±10 % of the group median."""
    amounts = [float(tx.amount) for tx in txs]
    med = median(amounts)
    if med == 0:
        return False
    return all(abs(a - med) / med <= _AMOUNT_TOLERANCE for a in amounts)


def apply_recurring_tags(user_id: int, db: Session) -> dict:
    """Detect recurring merchant groups and apply the 'recurring' tag.

    Heuristic thresholds (F32, agreed 2026-06-22):
      - Minimum occurrences : ≥3 transactions in the normalised-description group
      - Amount tolerance    : each amount within ±10 % of the group median
      - Cadence             : monthly (≥3 distinct months, day-of-month ±3 days)
                              OR weekly (median inter-arrival ≤ 10 days)

    Description grouping reuses _normalise() — no second matching engine.
    Tag persistence reuses app.services.tags.resolve_tag (F29 find-or-create).

    The function is idempotent: re-running never duplicates the tag or creates
    duplicate Tag rows (find-or-create + M2M append guard).

    Returns: {"tagged_transactions": int, "recurring_groups": int}
    """
    # Lazy import to avoid any startup-time circular issues
    from app.services.tags import resolve_tag

    rows = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == "expense",
        )
        .order_by(Transaction.transaction_date.asc())
        .all()
    )

    # Group by normalised description (same engine as detect())
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for tx in rows:
        key = _normalise(tx.description)
        if len(key) < _MIN_MERCHANT_LEN or key in _NOISE:
            continue
        groups[key].append(tx)

    tagged_count = 0
    group_count = 0

    for merchant, txs in groups.items():
        # Gate 0 (F32-fu1): the user already rejected this group. Respect that
        # — without this the next import would silently re-apply the tag and
        # the review decision would never stick.
        if any(t.name == _REJECTED_TAG_NAME for tx in txs for t in tx.tags):
            continue
        # Gate 1: minimum occurrences
        if len(txs) < _MIN_OCCURRENCES:
            continue
        # Gate 2: amount consistency
        if not _within_amount_tolerance(txs):
            continue
        # Gate 3: cadence (monthly OR weekly)
        if not (_is_monthly(txs) or _is_weekly(txs)):
            continue

        group_count += 1
        # find-or-create the 'recurring' tag once per group pass
        tag = resolve_tag(user_id, _TAG_NAME, db)

        for tx in txs:
            if tag not in tx.tags:
                tx.tags.append(tag)
                tagged_count += 1

    if group_count > 0:
        db.commit()

    log.info(
        "apply_recurring_tags: user_id=%s groups=%s tagged_tx=%s",
        user_id, group_count, tagged_count,
    )
    return {"tagged_transactions": tagged_count, "recurring_groups": group_count}


# ---------------------------------------------------------------------------
# F32-fu1 — Review surface for auto-applied 'recurring' tags
# ---------------------------------------------------------------------------
#
# F32 applies the tag with no way to disagree with it. These helpers back a
# small review queue: list what was auto-tagged, then either confirm the group
# (accept the heuristic) or reject it (strip the tag).
#
# Grouping is by the SAME normalised description key apply_recurring_tags used,
# so a review row corresponds exactly to a decision the detector made — the
# user accepts or rejects the detector's own unit of work, not an arbitrary
# re-slice of it.


def _tagged_groups(user_id: int, db: Session) -> dict[str, list[Transaction]]:
    """Every transaction currently carrying the 'recurring' tag, grouped by
    the normalised merchant key."""
    from app.models.tag import Tag

    tag = (
        db.query(Tag)
        .filter(Tag.user_id == user_id, Tag.name == _TAG_NAME)
        .first()
    )
    if not tag:
        return {}

    groups: dict[str, list[Transaction]] = defaultdict(list)
    for tx in sorted(tag.transactions, key=lambda t: t.transaction_date):
        if tx.user_id != user_id:
            continue  # defensive: tags are user-scoped, but never cross tenants
        groups[_normalise(tx.description)].append(tx)
    return groups


def list_recurring_review(user_id: int, db: Session) -> list[dict]:
    """Auto-tagged recurring groups awaiting a decision.

    Groups where every transaction already carries 'recurring-confirmed' are
    omitted — the user has accepted those and does not want to be asked again.
    """
    results: list[dict] = []
    for merchant, txs in _tagged_groups(user_id, db).items():
        confirmed = all(
            any(t.name == _CONFIRMED_TAG_NAME for t in tx.tags) for tx in txs
        )
        if confirmed:
            continue
        amounts = [float(tx.amount) for tx in txs]
        results.append({
            "merchant": merchant,
            "transaction_count": len(txs),
            "median_amount": round(median(amounts), 2),
            "total_amount": round(sum(amounts), 2),
            "first_seen": txs[0].transaction_date,
            "last_seen": txs[-1].transaction_date,
            "transaction_ids": [tx.id for tx in txs],
        })

    # Biggest spend first — that's what a user wants to check hardest.
    results.sort(key=lambda r: r["total_amount"], reverse=True)
    return results


def resolve_recurring_group(
    user_id: int, merchant: str, action: str, db: Session
) -> dict:
    """Confirm or reject one auto-tagged group.

    confirm → add 'recurring-confirmed' so the group leaves the review queue.
    reject  → remove 'recurring', undoing the detector's decision.

    Idempotent in both directions. Returns the number of transactions changed;
    an unknown merchant yields 0 rather than an error, so a double-submit from
    a stale page is harmless.
    """
    if action not in ("confirm", "reject"):
        raise ValueError("action must be 'confirm' or 'reject'")

    from app.services.tags import resolve_tag

    txs = _tagged_groups(user_id, db).get(_normalise(merchant), [])
    if not txs:
        return {"merchant": merchant, "action": action, "transactions_updated": 0}

    changed = 0
    if action == "confirm":
        confirmed_tag = resolve_tag(user_id, _CONFIRMED_TAG_NAME, db)
        for tx in txs:
            if confirmed_tag not in tx.tags:
                tx.tags.append(confirmed_tag)
                changed += 1
    else:
        rejected_tag = resolve_tag(user_id, _REJECTED_TAG_NAME, db)
        for tx in txs:
            recurring = next((t for t in tx.tags if t.name == _TAG_NAME), None)
            if recurring is not None:
                tx.tags.remove(recurring)
                changed += 1
            # Drop a stale confirmation so the two markers can't disagree.
            stale = next((t for t in tx.tags if t.name == _CONFIRMED_TAG_NAME), None)
            if stale is not None:
                tx.tags.remove(stale)
            # Persist the rejection so the next import does not re-tag it.
            if rejected_tag not in tx.tags:
                tx.tags.append(rejected_tag)
                changed = changed or 1

    if changed:
        db.commit()

    log.info(
        "resolve_recurring_group: user_id=%s merchant=%r action=%s updated=%s",
        user_id, merchant, action, changed,
    )
    return {"merchant": merchant, "action": action, "transactions_updated": changed}
