import calendar
from datetime import date
from decimal import Decimal

import numpy as np
from sqlalchemy.orm import Session

from app.models.transaction import Transaction, TransactionType

MIN_DATA_POINTS = 5


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def get_forecast(user_id: int, year: int, month: int, db: Session) -> dict:
    """
    Fit a linear model on daily cumulative expense spend for the given month
    and project the total to month-end.

    Returns a dict matching ForecastOut schema.
    """
    month_str = f"{year}-{month:02d}"

    rows = (
        db.query(Transaction.transaction_date, Transaction.amount)
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.expense,
            Transaction.transaction_date >= date(year, month, 1),
            Transaction.transaction_date <= date(year, month, _days_in_month(year, month)),
        )
        .order_by(Transaction.transaction_date)
        .all()
    )

    if not rows:
        return {
            "month": month_str,
            "projected_total": None,
            "confidence": "low",
            "data_points_used": 0,
            "reason": "insufficient_data",
        }

    # Aggregate by day → daily totals
    daily: dict[int, float] = {}
    for tx_date, amount in rows:
        day = tx_date.day
        daily[day] = daily.get(day, 0.0) + float(amount)

    # Build cumulative series over the days observed
    sorted_days = sorted(daily.keys())
    cumulative = 0.0
    days_x: list[float] = []
    cum_y: list[float] = []
    for d in sorted_days:
        cumulative += daily[d]
        days_x.append(float(d))
        cum_y.append(cumulative)

    data_points = len(days_x)

    if data_points < MIN_DATA_POINTS:
        return {
            "month": month_str,
            "projected_total": None,
            "confidence": "low",
            "data_points_used": data_points,
            "reason": "insufficient_data",
        }

    # Linear fit: cumulative_spend = slope * day + intercept
    x = np.array(days_x, dtype=float)
    y = np.array(cum_y, dtype=float)
    coeffs = np.polyfit(x, y, deg=1)
    slope, intercept = coeffs[0], coeffs[1]

    total_days = float(_days_in_month(year, month))
    projected = slope * total_days + intercept

    # Clamp: never project less than what's already spent
    projected = max(projected, cum_y[-1])

    # Confidence: based on R² of the fit
    y_pred = slope * x + intercept
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    if r_squared >= 0.85:
        confidence = "high"
    elif r_squared >= 0.60:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "month": month_str,
        "projected_total": Decimal(str(round(projected, 2))),
        "confidence": confidence,
        "data_points_used": data_points,
        "reason": None,
    }
