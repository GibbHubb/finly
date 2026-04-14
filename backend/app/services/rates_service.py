"""Exchange rate service — proxies Frankfurter API with a 1-hour in-memory cache."""
import time
from typing import Any
import httpx

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
