from fastapi import APIRouter

from app.api.v1.endpoints import auth, budgets, forecast, transactions, rates

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(forecast.router)
api_router.include_router(transactions.router)
api_router.include_router(budgets.router)
api_router.include_router(rates.router)
