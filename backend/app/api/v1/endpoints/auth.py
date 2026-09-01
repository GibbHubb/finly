from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.user import Token, UserCreate, UserOut, UserUpdate
from app.services.auth import (
    demo_login, get_current_user, login_user, register_user, update_user,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user account."""
    return register_user(data, db)


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Authenticate and receive a JWT access token."""
    return login_user(form.username, form.password, db)


@router.post("/demo-login", response_model=Token)
def demo_login_route(db: Session = Depends(get_db)):
    """F33 — log into the shared, auto-resetting demo account.

    Deliberately takes no credentials: the point is a recruiter clicking one
    button. That is exactly why it is gated — when DEMO_MODE is off this
    returns 404 (not 403), mirroring the /test/* guard, so a production deploy
    does not even advertise that a passwordless login exists.
    """
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Not found")
    return demo_login(db)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return current_user


@router.patch("/me", response_model=UserOut)
def update_me(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the current user's name or password."""
    return update_user(current_user, data, db)
