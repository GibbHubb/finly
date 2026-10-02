"""F60 — the login lockout is atomic under real parallelism.

F42's counter was count-then-insert: N parallel wrong guesses all read "4
failures" before any inserted, so a burst could exceed the threshold before the
429 engaged. The race only exists on Postgres (SQLite serialises writers), so
the real-race test needs a Postgres URL:

    docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=finly_race postgres:16
    FINLY_TEST_PG_URL=postgresql+psycopg2://postgres:pw@localhost:55432/finly_race pytest tests/test_login_lockout_race_f60.py

Without the env var that test is skipped (it is NOT silently green: it reports
as skipped). The SQLite tests below always run.
"""
import os
import unittest.mock as mock
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.services.auth as auth_module
from app.core.security import hash_password
from app.db.session import Base
from app.models.login_attempt import LoginAttempt
from app.models.user import User

PG_URL = os.environ.get("FINLY_TEST_PG_URL")
BURST = 20


@pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason="asserts the SQLite no-op; on the Postgres job the lock is real and the race tests below cover it",
)
def test_serialise_is_a_noop_on_sqlite(db):
    with mock.patch.object(db, "execute") as ex:
        auth_module._serialise_login_attempts(db, "a@finly.dev")
    ex.assert_not_called()


def test_serialise_takes_an_advisory_lock_on_postgres():
    session = mock.Mock()
    session.get_bind.return_value.dialect.name = "postgresql"
    auth_module._serialise_login_attempts(session, "a@finly.dev")
    sql = str(session.execute.call_args[0][0])
    assert "pg_advisory_xact_lock" in sql
    assert session.execute.call_args[0][1] == {"k": "login:a@finly.dev"}


def test_sequential_lockout_still_works_on_sqlite(client):
    email = "f60-seq@finly.dev"
    client.post("/api/v1/auth/register", json={"email": email, "password": "correct-horse-1", "full_name": "x"})
    codes = [
        client.post("/api/v1/auth/login", data={"username": email, "password": "wrong"}).status_code
        for _ in range(7)
    ]
    assert codes == [401] * 5 + [429] * 2


def _burst(url, serialise=True):
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with Session() as s:
        s.add(User(email="race@finly.dev", hashed_password=hash_password("right-pass-1"), full_name="r"))
        s.commit()

    def attempt(_):
        with Session() as s:
            try:
                auth_module.login_user("race@finly.dev", "wrong", s)
            except HTTPException as e:
                return e.status_code
        return 200

    patch = mock.patch.object(auth_module, "_serialise_login_attempts", lambda *a: None)
    try:
        if not serialise:
            patch.start()
        with ThreadPoolExecutor(BURST) as pool:
            codes = list(pool.map(attempt, range(BURST)))
    finally:
        if not serialise:
            patch.stop()
    with Session() as s:
        rows = s.scalar(select(func.count()).select_from(LoginAttempt))
    Base.metadata.drop_all(engine)
    engine.dispose()
    return codes, rows


@pytest.mark.skipif(not PG_URL, reason="needs FINLY_TEST_PG_URL (a real Postgres) to race")
def test_parallel_burst_never_exceeds_threshold_on_postgres():
    codes, rows = _burst(PG_URL)
    assert codes.count(401) == auth_module.LOGIN_LOCKOUT_THRESHOLD, codes
    assert codes.count(429) == BURST - auth_module.LOGIN_LOCKOUT_THRESHOLD, codes
    assert rows == auth_module.LOGIN_LOCKOUT_THRESHOLD


@pytest.mark.skipif(not PG_URL, reason="needs FINLY_TEST_PG_URL (a real Postgres) to race")
def test_control_without_the_lock_the_burst_overshoots_on_postgres():
    """Load-bearing check: with the lock disabled the same burst exceeds 5, so
    the test above is genuinely sensitive to the fix. Retry a few times since a
    race is probabilistic."""
    for _ in range(5):
        codes, rows = _burst(PG_URL, serialise=False)
        if codes.count(401) > auth_module.LOGIN_LOCKOUT_THRESHOLD:
            return
    pytest.fail("could not provoke the race without the lock; the race test may be insensitive")
