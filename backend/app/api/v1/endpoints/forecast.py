from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.transaction import ForecastOut
from app.services.auth import get_current_user
from app.services.forecast_service import get_forecast

router = APIRouter(prefix="/transactions/forecast", tags=["forecast"])


@router.get("", response_model=ForecastOut)
def forecast_spend(
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    year: int = Query(..., ge=2000, description="4-digit year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Project end-of-month expense total using linear regression on
    daily cumulative spend for the given month/year.
    Returns null projected_total with reason='insufficient_data' if <5 data points.
    """
    return get_forecast(current_user.id, year, month, db)
