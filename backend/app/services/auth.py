from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    new_jti,
    verify_password,
)
from app.db.session import get_db
from app.models.login_attempt import LoginAttempt
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserUpdate

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# F42 — the DB-backed login lockout: the 6th failed attempt for one email
# inside the window is refused before a password comparison even runs.
LOGIN_LOCKOUT_WINDOW = timedelta(seconds=60)
LOGIN_LOCKOUT_THRESHOLD = 5  # this many prior failures -> the NEXT one is 429


def _issue_token_pair(user_id: int, db: Session) -> Token:
    """F42 — mint an access/refresh pair sharing one `jti` and store the
    refresh token's revocation row. The row IS the session: revoking it
    (logout, or reuse detection on refresh) kills both tokens at once,
    because `get_current_user` checks the access token's `jti` against it.
    """
    jti = new_jti()
    access_token = create_access_token(user_id, jti)
    refresh_token = create_refresh_token(user_id, jti)

    row = RefreshToken(
        user_id=user_id,
        jti=jti,
        token_hash=hash_token(refresh_token),
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(row)
    db.commit()
    return Token(access_token=access_token, refresh_token=refresh_token)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("typ") != "access":
            # F42 — a refresh token is a different capability (14 days,
            # single-use) and must never be accepted where an access token
            # is expected.
            raise credentials_exception
        user_id = int(payload["sub"])
        jti = payload["jti"]
    except (ValueError, KeyError):
        raise credentials_exception

    # F42 — the revocation check AND the user lookup in ONE query, not two.
    # This runs on every authenticated request, and F44's query budget is a
    # real constraint: two separate queries here pushed
    # test_listing_100_tagged_transactions_is_not_n_plus_one from 3 to 4.
    # The join gets both facts — "does this session still exist and is it
    # revoked" and "who is the user" — in a single round trip, so the
    # pre-F42 budget holds exactly.
    row = (
        db.query(User, RefreshToken.revoked_at)
        .join(RefreshToken, RefreshToken.user_id == User.id)
        .filter(User.id == user_id, RefreshToken.jti == jti)
        .first()
    )
    if row is None:
        raise credentials_exception
    user, revoked_at = row
    if revoked_at is not None or not user.is_active:
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


def _serialise_login_attempts(db: Session, email: str) -> None:
    """F60 — make count-then-insert atomic per email.

    Without this, N parallel wrong guesses all read "4 failures" before any of
    them inserts, so a burst can exceed the threshold before the 429 engages.
    On Postgres a transaction-scoped advisory lock keyed on the email makes
    concurrent attempts for the same email queue up: the next one counts only
    after the previous one's failure row is committed. The lock releases at
    COMMIT/ROLLBACK, so every exit path of login_user must end the transaction.

    Different emails hash to different keys and do not block each other (a hash
    collision only causes a harmless extra wait). SQLite has no advisory locks
    and already serialises writers, so this is a no-op there (tests, local).
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"login:{email}"})


_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    """A real bcrypt hash of a random value, made once, for unknown-email logins to check against."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(new_jti())
    return _DUMMY_HASH


def lockout_key(email: str) -> str:
    """F63 — the lockout counter's key. `Bob@x.com`, `bob@x.com` and ` bob@x.com `
    share one counter, so an attacker cannot buy 5 fresh guesses per casing.

    Only the COUNTER is normalised. The account lookup stays an exact match on
    what was registered: making login case-insensitive is an identity change
    (registration would have to normalise too, plus a lower(email) unique
    index), not lockout hardening.
    """
    return email.strip().lower()


def login_user(email: str, password: str, db: Session, now: datetime | None = None) -> Token:
    """F42 — DB-backed lockout in front of the password check.

    F63 — the attempt is RESERVED before the password is checked, and the
    advisory lock covers only the reservation (count + insert), not bcrypt:

      1. lock(key) -> count recent attempts -> >= threshold: 429
      2. insert this attempt's row, read the user's hash -> COMMIT
         (releases the lock AND hands the pooled connection back)
      3. bcrypt, holding no lock and no connection
      4. right password: delete the reserved row, issue the pair;
         wrong password: the row stays as the failure, 401.

    The 5-then-429 guarantee holds because the count a request sees under the
    lock includes every attempt reserved before it, finished or still in
    bcrypt: at most THRESHOLD attempts per key per window ever reach step 3.
    Cost: while five logins are mid-bcrypt a sixth concurrent one is refused
    even if some of the five turn out correct. That errs on the safe side and
    lasts as long as one bcrypt.

    `now` is an injection point for the fixed-clock test, not a real caller
    argument — production always mints it here from the wall clock.
    """
    now = now or datetime.utcnow()
    window_start = now - LOGIN_LOCKOUT_WINDOW
    key = lockout_key(email)
    _serialise_login_attempts(db, key)
    recent_attempts = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.email == key, LoginAttempt.created_at >= window_start)
        .count()
    )
    if recent_attempts >= LOGIN_LOCKOUT_THRESHOLD:
        # F42 — refused BEFORE the password is even checked: a correct 6th
        # guess must not be rewarded with a login, or the lockout leaks
        # whether the attacker just found the right password.
        db.rollback()  # release the advisory lock before answering
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again in a minute.",
        )

    attempt = LoginAttempt(email=key, created_at=now)
    db.add(attempt)
    db.flush()
    # Read every value needed after the commit NOW: touching an expired ORM
    # attribute after commit would lazily open a new transaction, i.e. check a
    # pooled connection back out for the whole bcrypt.
    attempt_id = attempt.id
    user = db.query(User).filter(User.email == email).first()
    user_id, hashed = (user.id, user.hashed_password) if user else (None, None)
    db.commit()  # the reservation is now visible to the next waiter; lock + connection released

    if user_id is None or hashed is None:
        # Spend the same bcrypt time as a real check, so an unknown email is not
        # distinguishable from a wrong password by response time (F63 review).
        verify_password(password, _dummy_hash())
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(password, hashed):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # A success is not a failure: hand the reserved slot back.
    db.query(LoginAttempt).filter(LoginAttempt.id == attempt_id).delete(synchronize_session=False)
    return _issue_token_pair(user_id, db)  # its commit also commits the delete


def demo_login(db: Session) -> Token:
    """F33 — mint a token for the shared demo account, no credentials needed.

    The seed is ensured here rather than relying solely on the startup hook, so
    a cold free-tier instance whose database was re-provisioned still serves a
    working demo on the first click instead of an empty dashboard.

    The caller (the endpoint) is responsible for the DEMO_MODE gate — this
    helper is not safe to expose unguarded, since it hands out a valid session
    to anyone who asks.
    """
    from app.services.demo_seed import seed_demo

    user = seed_demo(db)
    return _issue_token_pair(user.id, db)


def refresh_session(refresh_token: str, db: Session) -> Token:
    """F42 — rotate: consume the presented refresh token, mint a new pair.

    Reuse detection: a refresh token whose row is ALREADY revoked has been
    presented before (a replay of a stolen or previously-rotated token) —
    the standard response is to revoke the rest of that user's active
    sessions too, not just refuse this one request.

    The "is it already revoked" check and the "consume it" write are ONE
    atomic UPDATE, not a read-then-write (code-review catch). finly's own
    architecture note in login_attempt.py is the reason this matters here
    too: a Vercel deployment is many containers hitting the same database in
    real parallel, not one process serialising requests. Two near-
    simultaneous presentations of the same still-valid token — a genuine
    thief racing the real client, or just a network retry — must not both
    be able to read "not revoked yet" and both succeed; only the UPDATE
    that actually flips `revoked_at` NULL -> now wins the row.
    """
    credentials_exception = HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        payload = decode_token(refresh_token)
        if payload.get("typ") != "refresh":
            raise credentials_exception
        user_id = int(payload["sub"])
        jti = payload["jti"]
    except (ValueError, KeyError):
        raise credentials_exception

    row = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if row is None or row.token_hash != hash_token(refresh_token):
        raise credentials_exception

    if row.expires_at < datetime.utcnow():
        raise credentials_exception

    now = datetime.utcnow()
    claim = db.execute(
        sa_update(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()

    if claim.rowcount == 0:
        # Lost the race (or a straightforward replay of an already-consumed
        # token) — somebody else already claimed this row. Kill every other
        # still-active session for this user: the token store may have been
        # stolen, and reuse is the standard signal for that.
        db.query(RefreshToken).filter(
            RefreshToken.user_id == row.user_id,
            RefreshToken.revoked_at.is_(None),
        ).update({"revoked_at": now}, synchronize_session=False)
        db.commit()
        raise credentials_exception

    new_pair = _issue_token_pair(user_id, db)
    row.revoked_at = now  # keep the in-memory object consistent with the atomic UPDATE above
    row.replaced_by = decode_token(new_pair.access_token)["jti"]
    db.commit()
    return new_pair


def logout_session(refresh_token: str, db: Session) -> None:
    """F42 — revoke the session the presented refresh token belongs to.

    This kills the refresh token AND the access token minted alongside it
    (they share `jti`), even though the access token's own `exp` has not
    passed — that is the whole point of the revocation-row check in
    `get_current_user`.
    """
    try:
        payload = decode_token(refresh_token)
        jti = payload["jti"]
    except (ValueError, KeyError):
        # An already-garbage token has nothing to revoke; logout is
        # idempotent either way, so this is not an error the caller needs.
        return

    row = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        db.commit()


def update_user(user: User, data: UserUpdate, db: Session) -> User:
    from app.services.rates_service import SUPPORTED_CURRENCIES
    from app.services.transactions import plan_base_amounts

    # Validate everything before changing anything.
    new_base_currency = None
    if data.base_currency is not None:
        new_cur = data.base_currency.upper()
        if new_cur not in SUPPORTED_CURRENCIES:
            raise HTTPException(status_code=400, detail=f"Unsupported currency: {new_cur}")
        if new_cur != user.base_currency:
            new_base_currency = new_cur

    if data.new_password is not None:
        if not data.current_password:
            raise HTTPException(status_code=400, detail="current_password is required to set a new password")
        if not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    # F55 — price every transaction in the new currency FIRST. This used to commit the new
    # currency and only then recompute, so an FX outage left the currency changed, every
    # converted base_amount NULLed, a 200 response, and no retry (re-selecting the same
    # currency is a no-op). plan_base_amounts raises 503 before anything is written, and the
    # whole request is refused — name and password included — so "nothing changed" is true.
    planned = plan_base_amounts(user.id, new_base_currency, db) if new_base_currency else []

    if data.full_name is not None:
        user.full_name = data.full_name
    if new_base_currency is not None:
        user.base_currency = new_base_currency
    if data.new_password is not None:
        user.hashed_password = hash_password(data.new_password)
    for tx, new_val in planned:
        tx.base_amount = new_val

    # One commit: the new currency and every re-priced row land together or not at all.
    db.commit()
    db.refresh(user)
    return user
