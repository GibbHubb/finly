"""Exchange rate service — Frankfurter proxy (live rates, in-memory cache)
plus historical per-date rates cached in the fx_rates DB table (F12).

F52 (2026-09-16): Frankfurter moved to api.frankfurter.dev/v1 and the old host answers
**301**. `httpx.get` does not follow redirects, both fetches swallowed the error with a
bare `except Exception`, and the caller then fell back to IDENTITY rates — so a 120.00 USD
expense was stored as `base_amount = 120.00` and every budget, alert and trend read that
number as euros. Three things changed: the new host, one client that follows redirects, and
a failure that is LOUD and yields **no rate** instead of a fake 1:1 conversion.
"""
import logging
import time
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.fx_rate import FxRate

logger = logging.getLogger(__name__)

# api.frankfurter.app now 301s here. Following redirects as well as pointing at the new
# host means the next move by the provider does not reopen this.
FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"

# What a bad upstream can throw. `Decimal("null")` raises InvalidOperation, which is an
# ArithmeticError and NOT a ValueError; a non-dict JSON body raises AttributeError or
# TypeError. Narrowing to httpx.HTTPError alone turned a bad payload into a 500 where the
# old bare `except Exception` degraded (review, 2026-09-16).
_FETCH_ERRORS = (httpx.HTTPError, ValueError, ArithmeticError, AttributeError, TypeError)

# One client, module level, so tests can drive the REAL request code through
# httpx.MockTransport instead of stubbing the fetch function (which is how the 301 stayed
# invisible to a green suite for two weeks).
_CLIENT = httpx.Client(follow_redirects=True, timeout=5.0)


def _get(url: str, params: dict) -> httpx.Response:
    """GET with ONE retry on a transport error (F54).

    `_CLIENT`'s keep-alive pool survives a Vercel freeze, so the first request after a thaw
    can land on a socket the far end already closed: ConnectError / ReadError /
    RemoteProtocolError. That is not the provider being down, and without a retry it left
    the caller with no rate (a NULL base_amount, or a refused save since F55). A status
    error (4xx/5xx) is NOT retried: the provider answered, and retrying doubles an outage.
    """
    try:
        return _CLIENT.get(url, params=params)
    except httpx.TransportError as exc:
        logger.info("FX: transport error on first attempt, retrying once (%s): %s", url, exc)
        return _CLIENT.get(url, params=params)


_CACHE: dict[str, Any] = {}
_CACHE_TTL = 3600  # seconds

SUPPORTED_CURRENCIES = ["EUR", "USD", "GBP", "SEK", "NOK", "DKK"]


def _cache_key(base: str) -> str:
    return base.upper()


def _is_fresh(entry: dict) -> bool:
    return time.time() - entry["ts"] < _CACHE_TTL


def get_rates(base: str = "EUR") -> dict[str, float]:
    """Return exchange rates for *base* currency against all supported symbols.

    Uses Frankfurter (https://api.frankfurter.dev/v1) — free, no API key required.

    F52 — on failure this returns **{}**, not identity rates: "we could not get a rate" must
    never be served as "1 USD = 1 EUR". The failure is not cached either, so the next caller
    retries instead of inheriting an hour of silence.
    """
    key = _cache_key(base)
    entry = _CACHE.get(key)
    if entry and _is_fresh(entry):
        return entry["rates"]

    symbols = ",".join(c for c in SUPPORTED_CURRENCIES if c != base.upper())
    url = f"{FRANKFURTER_BASE}/latest"
    try:
        resp = _get(url, {"from": base.upper(), "to": symbols})
        resp.raise_for_status()
        data = resp.json()
        rates: dict[str, float] = {base.upper(): 1.0}
        rates.update(data.get("rates", {}))
    except _FETCH_ERRORS as exc:
        # F52 — say so, and do NOT cache the failure: the next caller retries instead of
        # inheriting an hour-long identity table. Returns {} (not a partial dict holding
        # only the base at 1.0), so a caller cannot mistake a failure for a rate table.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("FX: live rate fetch failed (%s status=%s): %s", url, status, exc)
        return {}

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
    url = f"{FRANKFURTER_BASE}/{d.isoformat()}"
    try:
        resp = _get(url, {"from": "EUR", "to": symbols})
        resp.raise_for_status()
        data = resp.json()
        out: dict[str, Decimal] = {"EUR": Decimal("1")}
        for cur, rate in (data.get("rates") or {}).items():
            out[cur] = Decimal(str(rate))
        return out
    except _FETCH_ERRORS as exc:
        # F52 — a swallowed failure here is what made every conversion silently wrong.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("FX: historical rate fetch failed (%s status=%s): %s", url, status, exc)
        return {}


def _load_cached_rates_for_date(db: Session, d: date) -> dict[str, Decimal]:
    rows = db.query(FxRate).filter(FxRate.rate_date == d).all()
    return {r.currency: r.rate_vs_eur for r in rows}


def _persist_rates(db: Session, d: date, rates: dict[str, Decimal]) -> None:
    """Cache one date's rates. Tolerates a concurrent writer (F45).

    Two requests converting on the same new date both miss the cache, both fetch, and both
    insert. `uq_fx_rates_date_currency` rejects the second, which used to surface as an
    IntegrityError — a 500 from whatever endpoint was converting. The rates are the same
    published ECB numbers either way, so the loser simply keeps the winner's rows.
    """
    rows = [{"rate_date": d, "currency": cur, "rate_vs_eur": rate} for cur, rate in rates.items()]
    if not rows:
        return
    dialect = db.get_bind().dialect.name
    conflict = ["rate_date", "currency"]
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        db.execute(pg_insert(FxRate).values(rows).on_conflict_do_nothing(index_elements=conflict))
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        db.execute(sqlite_insert(FxRate).values(rows).on_conflict_do_nothing(index_elements=conflict))
    else:  # pragma: no cover — finly runs on exactly these two
        raise NotImplementedError(f"_persist_rates: no conflict-tolerant insert for {dialect}")
    db.commit()


def _ensure_rates_for_date(db: Session, d: date) -> dict[str, Decimal]:
    """Return {currency -> rate_vs_eur} for date `d`, fetching + caching on miss.

    F52 — returns **{}** when the rate cannot be obtained. It used to return identity
    rates, which turned "we do not know" into "1 USD = 1 EUR" and wrote that number into
    `base_amount` where nothing could ever find it again.
    """
    cached = _load_cached_rates_for_date(db, d)
    if cached:
        return cached

    fetched = _fetch_historical_eur_rates(d)
    # `{"EUR": 1}` is truthy but carries no usable rate. Persisting that would cache a
    # useless row and short-circuit every later fetch for this date (review, 2026-09-16).
    if any(cur != "EUR" for cur in fetched):
        _persist_rates(db, d, fetched)
        return fetched

    return {}


def convert_amount(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    on_date: date,
    db: Session,
    rate_memo: dict | None = None,
) -> Decimal | None:
    """Convert `amount` from `from_currency` to `to_currency` on `on_date`.

    Uses EUR as the pivot. Returns `amount` unchanged when from == to.

    Returns **None** — never a guessed rate — when either currency is unsupported or when no
    rate can be obtained for `on_date` (provider down, empty payload). This is the decision
    F47 asked for and F52 made: the old identity fallback stored 100 USD as 100.00 EUR,
    indistinguishable forever from a real 1:1 rate. Callers either refuse the write with a
    503 (F55, F57) or store nothing; see docs/technical/api.md "Currency conversion".
    """
    src = (from_currency or "EUR").upper()
    dst = (to_currency or "EUR").upper()
    if src not in SUPPORTED_CURRENCIES or dst not in SUPPORTED_CURRENCIES:
        return None
    if src == dst:
        return amount.quantize(Decimal("0.01"))

    # F44 — a caller converting many rows can pass `rate_memo` so each date is looked up once.
    if rate_memo is not None:
        if on_date not in rate_memo:
            rate_memo[on_date] = _ensure_rates_for_date(db, on_date)
        rates = rate_memo[on_date]
    else:
        rates = _ensure_rates_for_date(db, on_date)
    src_rate = rates.get(src)
    dst_rate = rates.get(dst)
    # F52 — no rate means NO NUMBER. The caller stores NULL, every reader coalesces to the
    # raw amount, and the gap stays countable instead of masquerading as a conversion.
    if not src_rate or not dst_rate:
        logger.warning("FX: no rate for %s->%s on %s — base_amount left unset", src, dst, on_date)
        return None
    # amount (src) / src_rate = EUR; then EUR * dst_rate = dst
    in_eur = Decimal(amount) / src_rate
    converted = in_eur * dst_rate
    return converted.quantize(Decimal("0.01"))
