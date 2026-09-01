"""Exchange rate service — Frankfurter proxy (live rates, in-memory cache)
plus historical per-date rates cached in the fx_rates DB table (F12)."""
import time
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.fx_rate import FxRate

_CACHE: dict[str, Any] = {}
_CACHE_TTL = 3600  # seconds

SUPPORTED_CURRENCIES = ["EUR", "USD", "GBP", "SEK", "NOK", "DKK"]


def _cache_key(base: str) -> str:
    return base.upper()


def _is_fresh(entry: dict) -> bool:
    return time.time() - entry["ts"] < _CACHE_TTL


def get_rates(base: str = "EUR") -> dict[str, float]:
    """Return exchange rates for *base* currency against all supported symbols.

    Uses Frankfurter (https://api.frankfurter.app) — free, no API key required.
    Falls back to identity rates (1.0) if the upstream is unreachable.
    """
    key = _cache_key(base)
    entry = _CACHE.get(key)
    if entry and _is_fresh(entry):
        return entry["rates"]

    symbols = ",".join(c for c in SUPPORTED_CURRENCIES if c != base.upper())
    try:
        resp = httpx.get(
            f"https://api.frankfurter.app/latest",
            params={"from": base.upper(), "to": symbols},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        rates: dict[str, float] = {base.upper(): 1.0}
        rates.update(data.get("rates", {}))
    except Exception:
        # Graceful fallback — all conversions become identity
        rates = {c: 1.0 for c in SUPPORTED_CURRENCIES}

    _CACHE[key] = {"ts": time.time(), "rates": rates}
    return rates


# ---------------------------------------------------------------------------
# Historical per-date rates (F12 — DB cache on top of Frankfurter)
# ---------------------------------------------------------------------------


def _fetch_historical_eur_rates(d: date) -> dict[str, Decimal]:
    """Fetch EUR→{supported} rates for a specific date from Frankfurter.
    Returns {} on any upstream failure so callers can fall back gracefully.
    """
    symbols = ",".join(c for c in SUPPORTED_CURRENCIES if c != "EUR")
    try:
        resp = httpx.get(
            f"https://api.frankfurter.app/{d.isoformat()}",
            params={"from": "EUR", "to": symbols},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        out: dict[str, Decimal] = {"EUR": Decimal("1")}
        for cur, rate in (data.get("rates") or {}).items():
            out[cur] = Decimal(str(rate))
        return out
    except Exception:
        return {}


def _load_cached_rates_for_date(db: Session, d: date) -> dict[str, Decimal]:
    rows = db.query(FxRate).filter(FxRate.rate_date == d).all()
    return {r.currency: r.rate_vs_eur for r in rows}


def _persist_rates(db: Session, d: date, rates: dict[str, Decimal]) -> None:
    for cur, rate in rates.items():
        db.add(FxRate(rate_date=d, currency=cur, rate_vs_eur=rate))
    db.commit()


def _ensure_rates_for_date(db: Session, d: date) -> dict[str, Decimal]:
    """Return {currency -> rate_vs_eur} for date `d`, fetching + caching on miss.
    If the upstream is down and no cached rates exist, returns identity rates
    so callers can still compute a best-effort base_amount.
    """
    cached = _load_cached_rates_for_date(db, d)
    if cached:
        return cached

    fetched = _fetch_historical_eur_rates(d)
    if fetched:
        _persist_rates(db, d, fetched)
        return fetched

    # Graceful degradation: identity for all supported currencies.
    return {c: Decimal("1") for c in SUPPORTED_CURRENCIES}


def convert_amount(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    on_date: date,
    db: Session,
) -> Decimal | None:
    """Convert `amount` from `from_currency` to `to_currency` on `on_date`.

    Uses EUR as the pivot. Returns None if either currency isn't supported;
    returns `amount` unchanged when from == to.
    """
    src = (from_currency or "EUR").upper()
    dst = (to_currency or "EUR").upper()
    if src not in SUPPORTED_CURRENCIES or dst not in SUPPORTED_CURRENCIES:
        return None
    if src == dst:
        return amount.quantize(Decimal("0.01"))

    rates = _ensure_rates_for_date(db, on_date)
    src_rate = rates.get(src, Decimal("1"))
    dst_rate = rates.get(dst, Decimal("1"))
    if src_rate == 0:
        return None
    # amount (src) / src_rate = EUR; then EUR * dst_rate = dst
    in_eur = Decimal(amount) / src_rate
    converted = in_eur * dst_rate
    return converted.quantize(Decimal("0.01"))
