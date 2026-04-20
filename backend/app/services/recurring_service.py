"""Detect recurring (subscription-like) transactions from spending history."""
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import median

from sqlalchemy.orm import Session

from app.models.transaction import Transaction

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
