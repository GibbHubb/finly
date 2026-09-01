"""Exchange rate proxy endpoint."""
from fastapi import APIRouter, Depends

from app.models.user import User
from app.services.auth import get_current_user
from app.services.rates_service import get_rates, SUPPORTED_CURRENCIES

router = APIRouter(prefix="/rates", tags=["rates"])


@router.get("/")
def exchange_rates(
    base: str = "EUR",
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return today's exchange rates for *base* currency.

    Rates are cached in-memory for 1 hour. Supported bases/symbols:
    EUR, USD, GBP, SEK, NOK, DKK.
    """
    if base.upper() not in SUPPORTED_CURRENCIES:
        base = "EUR"
    rates = get_rates(base)
    return {"base": base.upper(), "rates": rates, "currencies": SUPPORTED_CURRENCIES}
