"""F52 — the FX fetch itself, driven through a mocked transport.

Why this file exists: `test_multi_currency.py` stubs `_fetch_historical_eur_rates`, so the
suite has never executed the HTTP call. Frankfurter moved to `api.frankfurter.dev/v1` and
now answers **301** on the old host; `httpx.get` does not follow redirects by default and
both call sites swallowed the error, so every conversion silently fell back to identity and
a 120.00 USD expense was stored as `base_amount = 120.00` (proven against a running server
2026-09-15).

These tests exercise the REAL request code and assert the behaviour the fix must have:
  (i)   a 200 returns rates;
  (ii)  a 301 -> 200 is followed (the actual production shape);
  (iii) a 5xx yields NO rates, one WARNING, and `convert_amount` -> None (never identity);
  (iv)  a timeout behaves like (iii);
  (v)   a failed live fetch is not cached, so the next call retries.
"""
import logging
import os
import sys
from datetime import date
from decimal import Decimal

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import rates_service  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    rates_service._CACHE.clear()
    yield
    rates_service._CACHE.clear()


def _transport(handler):
    """Install a MockTransport on the service's client for one test."""
    return httpx.MockTransport(handler)


def _json_rates(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"amount": 1.0, "base": "EUR", "date": "2026-09-15",
                                     "rates": {"USD": 1.1551, "GBP": 0.85598}})


_REDIRECT_SEEN: list[str] = []


def _redirect_then_json(request: httpx.Request) -> httpx.Response:
    """A real 301 on the FIRST hop, whatever host the code calls.

    2026-09-16 review: this used to branch on `frankfurter.app`, but the fix points at
    `frankfurter.dev` — so no redirect was ever issued and the test passed even with
    follow_redirects=False. It now redirects the first request it sees and asserts the
    second one arrived, so the test genuinely exercises redirect-following."""
    url = str(request.url)
    if not _REDIRECT_SEEN:
        _REDIRECT_SEEN.append(url)
        return httpx.Response(301, headers={"location": url.replace("/v1/", "/v1/moved/")})
    return _json_rates(request)


def _server_error(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, text="upstream down")


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectTimeout("timed out", request=request)


# ── (i) the happy path ─────────────────────────────────────────────────────────
def test_historical_fetch_returns_rates(monkeypatch):
    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(_json_rates), follow_redirects=True))
    out = rates_service._fetch_historical_eur_rates(date(2026, 9, 15))
    assert out["USD"] == Decimal("1.1551")
    assert out["EUR"] == Decimal("1")


# ── (ii) the defect this ticket exists for ─────────────────────────────────────
def test_a_301_is_followed(monkeypatch):
    """Frankfurter's real answer on the old host. Without follow_redirects the fetch fails
    and the caller used to fall back to identity — the silent wrong number."""
    _REDIRECT_SEEN.clear()
    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(_redirect_then_json), follow_redirects=True))
    out = rates_service._fetch_historical_eur_rates(date(2026, 9, 15))
    assert _REDIRECT_SEEN, "no redirect was issued — this test would pass without following one"
    assert out and out["USD"] == Decimal("1.1551")


def test_a_301_kills_the_fetch_when_redirects_are_not_followed(monkeypatch):
    """The control for the test above. Every test here INJECTS its own client, so none of
    them can notice a misconfigured shipped client — that is what
    `test_the_service_client_follows_redirects_and_uses_the_new_host` is for. This proves
    the behaviour itself is falsifiable: with a non-following client the same 301 yields no
    rate at all, which is exactly what used to happen in production."""
    _REDIRECT_SEEN.clear()
    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(_redirect_then_json)))  # no follow
    out = rates_service._fetch_historical_eur_rates(date(2026, 9, 15))
    assert _REDIRECT_SEEN, "the transport never issued the 301"
    assert out == {}, "a 301 must kill the fetch when redirects are not followed"


# ── (iii)/(iv) a failure is LOUD and yields no rate — never identity ───────────
def test_a_server_error_yields_no_rates_and_warns(monkeypatch, caplog):
    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(_server_error), follow_redirects=True))
    with caplog.at_level(logging.WARNING):
        out = rates_service._fetch_historical_eur_rates(date(2026, 9, 15))
    assert out == {}
    assert any("frankfurter" in r.message.lower() or "rate" in r.message.lower()
               for r in caplog.records), "a swallowed FX failure must leave a WARNING"


def test_a_timeout_yields_no_rates_and_warns(monkeypatch, caplog):
    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(_timeout), follow_redirects=True))
    with caplog.at_level(logging.WARNING):
        out = rates_service._fetch_historical_eur_rates(date(2026, 9, 15))
    assert out == {}
    assert caplog.records, "a timeout must leave a WARNING"


def test_convert_amount_returns_none_when_the_rate_cannot_be_fetched(monkeypatch, db):
    """The heart of F52: no rate must mean NO NUMBER, not the raw amount dressed up as a
    conversion. `base_amount` then stays NULL and every reader coalesces to `amount`, so the
    screen is unchanged but the gap is countable."""
    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(_server_error), follow_redirects=True))
    out = rates_service.convert_amount(Decimal("120.00"), "USD", "EUR", date(2026, 9, 15), db)
    assert out is None


# ── review 2026-09-16: a bad payload must DEGRADE, not 500 ─────────────────────
def test_a_null_rate_in_the_payload_degrades_instead_of_raising(monkeypatch, caplog):
    """`Decimal("null")` raises InvalidOperation — an ArithmeticError, NOT a ValueError.
    The first narrowed `except` missed it, so a bad upstream payload became a 500 on
    transaction create where the old code degraded."""
    def null_rate(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"amount": 1.0, "base": "EUR", "rates": {"USD": None}})

    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(null_rate), follow_redirects=True))
    with caplog.at_level(logging.WARNING):
        out = rates_service._fetch_historical_eur_rates(date(2026, 9, 15))
    assert out == {}, "a null rate must degrade to 'no rates', not raise"


def test_a_non_dict_body_degrades_instead_of_raising(monkeypatch):
    def junk(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(junk), follow_redirects=True))
    assert rates_service._fetch_historical_eur_rates(date(2026, 9, 15)) == {}
    assert rates_service.get_rates("EUR") == {}


def test_an_empty_payload_is_not_persisted_to_the_rate_cache(monkeypatch, db):
    """`{"EUR": 1}` is truthy but holds no usable rate. Persisting it would cache a useless
    row and short-circuit every later fetch for that date — permanently, now that the
    identity fallback is gone."""
    from app.models.fx_rate import FxRate

    def empty_rates(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"amount": 1.0, "base": "EUR", "rates": {}})

    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(empty_rates), follow_redirects=True))
    d = date(2026, 9, 15)
    out = rates_service._ensure_rates_for_date(db, d)
    assert out == {} or all(c == "EUR" for c in out)
    assert db.query(FxRate).filter(FxRate.rate_date == d).count() == 0, (
        "an empty payload was cached — later fetches for this date can never succeed")


# ── the SHIPPED client, not the one these tests inject ─────────────────────────
def test_the_service_client_follows_redirects_and_uses_the_new_host():
    """Every test above injects its own client with follow_redirects=True, so not one of
    them would notice if the module's REAL client were built without it — which is exactly
    the defect F52 is about. Assert the shipped configuration itself."""
    assert rates_service._CLIENT.follow_redirects is True, (
        "the production client does not follow redirects: a 301 becomes 'no rate'")
    assert "frankfurter.dev" in rates_service.FRANKFURTER_BASE
    assert "frankfurter.app" not in rates_service.FRANKFURTER_BASE, (
        "the old host 301s; pointing at it relies entirely on redirect-following")


def test_no_call_site_bypasses_the_shared_client():
    """A bare httpx.get() would not follow redirects and would not carry the timeout."""
    src = open(rates_service.__file__, encoding="utf-8").read()
    assert "httpx.get(" not in src, "a call site bypasses _CLIENT — it will 301 silently"


# ── (v) a failure is not cached for an hour ────────────────────────────────────
def test_a_failed_live_fetch_is_not_cached(monkeypatch):
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="down")
        return httpx.Response(200, json={"amount": 1.0, "base": "EUR", "date": "2026-09-15",
                                         "rates": {"USD": 1.1551}})

    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=_transport(flaky), follow_redirects=True))
    first = rates_service.get_rates("EUR")
    second = rates_service.get_rates("EUR")
    assert calls["n"] == 2, "the failed fetch was cached — the next caller inherits it"
    assert second.get("USD") == 1.1551
    # Review 2026-09-16: the old assertion (`in (None, 1.0) or == {}`) passed even if the
    # failure path returned FULL identity rates — the exact regression F52 exists to stop.
    assert first == {}, "a failed live fetch must yield no rates at all, never a 1:1 table"
