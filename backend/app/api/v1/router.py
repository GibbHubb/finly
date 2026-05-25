from fastapi import APIRouter

from app.api.v1.endpoints import auth, bank, budgets, categorisation_rules, forecast, reports, savings_goals, tags, test_utils, transactions, rates
from app.core.config import settings

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(forecast.router)
api_router.include_router(transactions.router)
api_router.include_router(budgets.router)
api_router.include_router(rates.router)
api_router.include_router(savings_goals.router)
api_router.include_router(categorisation_rules.router)
api_router.include_router(bank.router)  # F27
api_router.include_router(reports.router)  # F28
api_router.include_router(tags.router)     # F29
# /test/* endpoints are gated by settings.E2E_MODE (each handler 404s when off).
if settings.E2E_MODE:
    api_router.include_router(test_utils.router)
