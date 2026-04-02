from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token, hash_password, verify_password, create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, Token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id = int(payload["sub"])
    except (ValueError, KeyError):
        raise credentials_exception

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise credentials_exception
    return user


def register_user(data: UserCreate, db: Session) -> User:
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(email: str, password: str, db: Session) -> Token:
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    return Token(access_token=token)


def update_user(user: User, data: UserUpdate, db: Session) -> User:
    if data.full_name is not None:
        user.full_name = data.full_name

    if data.new_password is not None:
        if not data.current_password:
            raise HTTPException(status_code=400, detail="current_password is required to set a new password")
        if not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.hashed_password = hash_password(data.new_password)

    db.commit()
    db.refresh(user)
    return user
