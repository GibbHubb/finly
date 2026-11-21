"""F64 — a correct password racing wrong ones that are still inside bcrypt.

Since F63 the advisory lock covers only the reservation (count + insert) and
bcrypt runs after the commit, with no lock held. So a correct login can arrive
while wrong guesses for the same email are mid-bcrypt. Two things must both hold:

  * under the limit, the correct login is not blocked or refused by them: it
    reserves its own slot, verifies, and gets its token pair;
  * at the limit (5 reserved, still in bcrypt), the correct login is refused
    with 429 BEFORE bcrypt, and stays refused once the five resolve as failures.

The interleaving is made deterministic rather than timing-based: a spy around
`verify_password` parks every "wrong" attempt inside bcrypt on an Event until
the test releases it. Each request runs in its own thread and session, on the
`db` fixture's engine, so this runs on SQLite by default and on a real Postgres
(real advisory locks, real parallel connections) under TEST_DATABASE_URL.

On the pre-F63 code the cap case fails: attempts were only recorded after
bcrypt, so with five wrong guesses in flight the count was still 0 and the
correct sixth login was let through. (On Postgres the pre-F63 lock was also
held through bcrypt, so the parked attempts would serialise and the test fails
on its timeouts instead of hanging.)
"""
import threading
import unittest.mock as mock
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

import app.services.auth as auth_module
from app.core.security import hash_password
from app.models.login_attempt import LoginAttempt
from app.models.user import User

EMAIL = "race-f64@finly.dev"
RIGHT = "right-pass-1"
WRONG = "wrong"
TIMEOUT = 15  # seconds; a failure, never a hang


class _Bcrypt:
    """Parks wrong-password checks inside bcrypt until released; counts every call."""

    def __init__(self):
        self.real = auth_module.verify_password
        self.parked = threading.Semaphore(0)
        self.release = threading.Event()
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def __call__(self, plain, hashed):
        with self.lock:
            self.calls.append(plain)
        if plain == WRONG:
            self.parked.release()
            if not self.release.wait(TIMEOUT):
                raise AssertionError("parked attempt was never released")
        return self.real(plain, hashed)

    def wait_parked(self, n):
        for i in range(n):
            if not self.parked.acquire(timeout=TIMEOUT):
                raise AssertionError(f"only {i} of {n} wrong attempts reached bcrypt")


def _attempt(bind, password):
    with Session(bind=bind) as s:
        try:
            auth_module.login_user(EMAIL, password, s)
        except HTTPException as e:
            return e.status_code
    return 200


@pytest.fixture
def user(db):
    db.add(User(email=EMAIL, hashed_password=hash_password(RIGHT), full_name="r"))
    db.commit()
    return db.get_bind()


def _with_parked_wrong(bind, n, while_parked):
    """Start n wrong logins, wait until all n are inside bcrypt, run while_parked(spy), release."""
    spy = _Bcrypt()
    with mock.patch.object(auth_module, "verify_password", spy), ThreadPoolExecutor(n) as pool:
        futures = [pool.submit(_attempt, bind, WRONG) for _ in range(n)]
        try:
            spy.wait_parked(n)
            result = while_parked(spy)
        finally:
            spy.release.set()
        wrong_codes = [f.result(timeout=TIMEOUT) for f in futures]
    return result, wrong_codes, spy


@pytest.mark.parametrize("in_flight", [1, 4])
def test_a_correct_login_succeeds_while_wrong_ones_are_in_bcrypt(db, user, in_flight):
    code, wrong_codes, spy = _with_parked_wrong(user, in_flight, lambda _spy: _attempt(user, RIGHT))
    assert code == 200
    assert wrong_codes == [401] * in_flight
    assert spy.calls.count(RIGHT) == 1
    # Each wrong guess left its failure row; the success gave its reserved slot back.
    assert db.query(LoginAttempt).count() == in_flight


def test_with_five_in_bcrypt_a_correct_login_is_refused_before_bcrypt(db, user):
    threshold = auth_module.LOGIN_LOCKOUT_THRESHOLD

    def correct_while_parked(spy):
        code = _attempt(user, RIGHT)
        return code, spy.calls.count(RIGHT)

    (code, right_checks), wrong_codes, spy = _with_parked_wrong(user, threshold, correct_while_parked)
    assert code == 429
    assert right_checks == 0, "the 6th attempt reached bcrypt: the lockout leaked a password check"
    assert wrong_codes == [401] * threshold
    assert db.query(LoginAttempt).count() == threshold  # the cap: exactly five attempts recorded

    # Once the five have resolved as failures, the account is still locked for the window.
    assert _attempt(user, RIGHT) == 429
    assert db.query(LoginAttempt).count() == threshold
