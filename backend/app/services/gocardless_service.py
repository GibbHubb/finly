"""F27 — Thin GoCardless Bank Account Data REST client.

No SDK; we hit /token/new + /requisitions + /accounts/{id}/transactions
directly. All API calls funnel through `_request()` which raises
GoCardlessError on non-2xx so callers can handle auth/consent failures.
Token is cached in-process for ~85 min (their tokens are 24h but we
re-mint conservatively).

ALL keys come from settings; nothing committed. App boots cleanly with
empty keys — endpoints just refuse with 503 until configured.
"""
from __future__ import annotations

import time
from typing import Any
import httpx

from app.core.config import settings


class GoCardlessError(Exception):
    """Raised on any non-2xx GoCardless response or missing credentials."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


# Module-level token cache: (token, mints-at-epoch). 85-minute TTL.
_token_cache: tuple[str, float] | None = None
_TOKEN_TTL_S = 85 * 60


def _credentials_configured() -> bool:
    return bool(settings.GOCARDLESS_SECRET_ID and settings.GOCARDLESS_SECRET_KEY)


def _require_credentials() -> None:
    if not _credentials_configured():
        raise GoCardlessError(
            "GoCardless credentials not configured — set GOCARDLESS_SECRET_ID and "
            "GOCARDLESS_SECRET_KEY in backend/.env",
            status=503,
        )


def _get_token() -> str:
    global _token_cache
    _require_credentials()
    if _token_cache is not None:
        token, minted = _token_cache
        if time.time() - minted < _TOKEN_TTL_S:
            return token
    r = httpx.post(
        f"{settings.GOCARDLESS_BASE_URL}/token/new/",
        json={
            "secret_id": settings.GOCARDLESS_SECRET_ID,
            "secret_key": settings.GOCARDLESS_SECRET_KEY,
        },
        timeout=15,
    )
    if r.status_code >= 300:
        raise GoCardlessError(f"token/new failed: {r.status_code} {r.text[:200]}", status=r.status_code)
    token = r.json().get("access")
    if not token:
        raise GoCardlessError("token/new returned no access token")
    _token_cache = (token, time.time())
    return token


def _request(method: str, path: str, **kwargs) -> Any:
    token = _get_token()
    headers = {**(kwargs.pop("headers", None) or {}), "Authorization": f"Bearer {token}"}
    r = httpx.request(
        method, f"{settings.GOCARDLESS_BASE_URL}{path}",
        headers=headers, timeout=30, **kwargs,
    )
    if r.status_code >= 300:
        raise GoCardlessError(
            f"{method} {path} failed: {r.status_code} {r.text[:300]}",
            status=r.status_code,
        )
    return r.json() if r.content else {}


def list_institutions(country: str = "NL") -> list[dict]:
    return _request("GET", "/institutions/", params={"country": country})


def create_requisition(institution_id: str, redirect: str | None = None) -> dict:
    """Create a requisition (consent flow). Returns the hosted consent link
    and the requisition_id we persist."""
    body = {
        "redirect": redirect or settings.GOCARDLESS_REDIRECT_URL,
        "institution_id": institution_id,
        "reference": f"finly-{int(time.time())}",
        "user_language": "EN",
    }
    return _request("POST", "/requisitions/", json=body)


def get_requisition(requisition_id: str) -> dict:
    return _request("GET", f"/requisitions/{requisition_id}/")


def fetch_transactions(account_id: str) -> dict:
    """Returns {transactions: {booked: [...], pending: [...]}}."""
    return _request("GET", f"/accounts/{account_id}/transactions/")
