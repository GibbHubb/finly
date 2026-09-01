"""E2E-only test utility endpoints.

Routes here are exposed *only* when `E2E_MODE` is set to true in settings.
They wipe and reseed deterministic test data so a Playwright suite can run
against a fresh, predictable backend on every CI invocation.

Never enable in production.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.models.budget import Budget
from app.models.categorisation_rule import CategorisationRule
from app.models.fx_rate import FxRate
from app.models.import_mapping import ImportMapping
from app.models.savings_goal import SavingsGoal
from app.models.transaction import Transaction
from app.models.user import User

router = APIRouter(prefix="/test", tags=["test"])

E2E_USER_EMAIL = "e2e@finly.dev"
E2E_USER_PASSWORD = "e2e-pass-123"
E2E_USER_NAME = "E2E User"


def _require_e2e_mode():
    if not settings.E2E_MODE:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/reset", status_code=200)
def reset_state(db: Session = Depends(get_db)):
    """Wipe all data and re-create the standard E2E test user."""
    _require_e2e_mode()
    # Order matters because of FKs.
    db.execute(delete(Transaction))
    db.execute(delete(Budget))
    db.execute(delete(SavingsGoal))
    db.execute(delete(CategorisationRule))
    db.execute(delete(ImportMapping))
    db.execute(delete(FxRate))
    db.execute(delete(User))
    db.commit()

    user = User(
        email=E2E_USER_EMAIL,
        hashed_password=hash_password(E2E_USER_PASSWORD),
        full_name=E2E_USER_NAME,
    )
    db.add(user)
    db.commit()
    return {"ok": True, "user_email": E2E_USER_EMAIL}


@router.get("/health")
def e2e_health():
    """Confirms E2E_MODE is on (404s when off — used by playwright globalSetup)."""
    _require_e2e_mode()
    return {"e2e_mode": True}
