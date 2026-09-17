"""F54 — a dead keep-alive socket after a serverless thaw gets ONE retry, not a silent NULL."""
from datetime import date

import httpx

from app.services import rates_service

RATES = {"amount": 1.0, "base": "EUR", "rates": {"USD": 1.1, "GBP": 0.85, "SEK": 11.5, "NOK": 11.3, "DKK": 7.45}}


def _client(monkeypatch, handler):
    rates_service._CACHE.clear()
    monkeypatch.setattr(rates_service, "_CLIENT",
                        httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))


def test_first_attempt_connect_error_then_success_gets_the_rate(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("connection reset after thaw", request=request)
        return httpx.Response(200, json=RATES)

    _client(monkeypatch, handler)
    assert rates_service.get_rates("EUR")["USD"] == 1.1
    assert calls["n"] == 2


def test_historical_fetch_also_retries_a_read_error(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadError("socket closed", request=request)
        return httpx.Response(200, json=RATES)

    _client(monkeypatch, handler)
    out = rates_service._fetch_historical_eur_rates(date(2026, 3, 5))
    assert str(out["USD"]) == "1.1" and calls["n"] == 2


def test_a_persistent_transport_failure_still_gives_up_after_two_attempts(monkeypatch):  # control
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("down", request=request)

    _client(monkeypatch, handler)
    assert rates_service.get_rates("EUR") == {}
    assert calls["n"] == 2


def test_a_status_error_is_not_retried(monkeypatch):  # the provider answered: retrying doubles an outage
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503, text="down")

    _client(monkeypatch, handler)
    assert rates_service.get_rates("EUR") == {}
    assert calls["n"] == 1
