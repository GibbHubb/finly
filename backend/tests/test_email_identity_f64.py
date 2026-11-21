"""F64 — one account per email, whatever its case.

F63 lowercased the lockout counter's key but left the account lookup an exact
match, and registration stored the email as typed (pydantic's EmailStr only
lowercases the domain). So `Bob@x` and `bob@x` could be two accounts sharing
one lockout counter. Now: registration stores the normalised email, login and
the duplicate check match on lower(email), and a unique index on lower(email)
makes the database refuse a case duplicate. A legacy row stored mixed-case is
not rewritten; it simply matches on lower(email) like everything else.
"""
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

import app.services.auth as auth_module
from app.core.security import hash_password
from app.models.user import User

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


def _register(client, email, password="right-pass-1"):
    return client.post(REGISTER, json={"email": email, "password": password, "full_name": "b"})


def _login(db, email, password="right-pass-1"):
    try:
        auth_module.login_user(email, password, db)
    except HTTPException as e:
        return e.status_code
    return 200


def _raw_user(db, email):
    """A row written straight to the table, as a pre-F64 registration would have left it."""
    db.add(User(email=email, hashed_password=hash_password("right-pass-1"), full_name="legacy"))
    db.commit()


def test_normalise_email_and_lockout_key_are_one_rule():
    assert auth_module.normalise_email("  Bob@Finly.DEV ") == "bob@finly.dev"
    assert auth_module.lockout_key("  Bob@Finly.DEV ") == auth_module.normalise_email("  Bob@Finly.DEV ")


def test_register_stores_the_email_lowercased(client, db):
    res = _register(client, "Bob@Finly.dev")
    assert res.status_code == 201, res.text
    assert res.json()["email"] == "bob@finly.dev"
    assert [u.email for u in db.query(User).all()] == ["bob@finly.dev"]


def test_register_refuses_a_case_variant_of_an_existing_email(client, db):
    _raw_user(db, "Bob@finly.dev")  # legacy mixed-case row
    res = _register(client, "bob@finly.dev")
    assert res.status_code == 400
    assert res.json()["detail"] == "Email already registered"
    assert db.query(User).count() == 1


@pytest.mark.parametrize("typed", ["bob@finly.dev", "BOB@finly.dev", "Bob@Finly.Dev", "  bob@finly.dev "])
def test_login_ignores_case(client, db, typed):
    assert _register(client, "bob@finly.dev").status_code == 201
    assert _login(db, typed) == 200


def test_a_legacy_mixed_case_row_logs_in_with_any_case(db):
    _raw_user(db, "Mixed@finly.dev")
    assert _login(db, "Mixed@finly.dev") == 200
    assert _login(db, "mixed@finly.dev") == 200
    assert _login(db, "MIXED@FINLY.DEV") == 200
    assert _login(db, "mixed@finly.dev", "wrong") == 401


def test_login_over_http_with_a_different_case(client):
    assert _register(client, "carol@finly.dev").status_code == 201
    res = client.post(LOGIN, data={"username": "Carol@Finly.dev", "password": "right-pass-1"})
    assert res.status_code == 200, res.text
    assert res.json()["access_token"]


def test_the_database_refuses_a_case_duplicate(db):
    """The unique index on lower(email): the guarantee that does not depend on
    every write path remembering to normalise."""
    _raw_user(db, "dup@finly.dev")
    db.add(User(email="DUP@finly.dev", hashed_password="x", full_name="d"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_registration_that_loses_the_race_gets_400_not_500(client, db, monkeypatch):
    """Two concurrent registrations of one email (any case) can both pass the
    pre-check; the index lets one in and the loser must get the same 400, not a
    500. Simulated by making the pre-check miss the row that is already there."""
    _raw_user(db, "Race@finly.dev")
    monkeypatch.setattr(auth_module, "find_user_by_email", lambda *a: None)
    res = _register(client, "race@finly.dev")
    assert res.status_code == 400
    assert res.json()["detail"] == "Email already registered"
    assert db.query(User).count() == 1


# --- the migration ------------------------------------------------------------

PREVIOUS_HEAD = "f45b0d9e7c1a"


def _alembic(url, fn, revision):
    from alembic import command
    from alembic.config import Config

    cfg = Config()  # no ini: see conftest._alembic_upgrade_head for why
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        getattr(command, fn)(cfg, revision)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _index_names(engine):
    # Straight from the catalogue: SQLAlchemy's inspector skips expression indexes on SQLite.
    with engine.connect() as conn:
        return set(conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'users'"
        )).scalars())


def test_migration_refuses_case_collisions_then_applies(tmp_path):
    """Runs the real migration chain on a throwaway SQLite file (never the
    suite's database). Two users colliding on lower(email): the upgrade raises,
    names the count, and leaves the schema untouched. Resolve the collision by
    hand and the same upgrade applies; downgrade removes the index again."""
    url = f"sqlite:///{(tmp_path / 'f64_migration.db').as_posix()}"
    _alembic(url, "upgrade", PREVIOUS_HEAD)
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            for email in ("Ann@finly.dev", "ann@finly.dev", "solo@finly.dev"):
                conn.execute(
                    text("INSERT INTO users (email, hashed_password, full_name, is_active) "
                         "VALUES (:e, 'x', 'n', 1)"),
                    {"e": email},
                )

        with pytest.raises(RuntimeError, match=r"F64: 1 email\(s\) .* nothing was changed"):
            _alembic(url, "upgrade", "head")
        assert "ix_users_email_lower" not in _index_names(engine)
        with engine.connect() as conn:  # no account was merged or deleted
            assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar() == 3

        with engine.begin() as conn:  # the human decision the error asks for
            conn.execute(text("DELETE FROM users WHERE email = 'Ann@finly.dev'"))
        _alembic(url, "upgrade", "head")
        assert "ix_users_email_lower" in _index_names(engine)
        with pytest.raises(IntegrityError), engine.begin() as conn:  # and it bites
            conn.execute(text("INSERT INTO users (email, hashed_password, full_name, is_active) "
                              "VALUES ('SOLO@finly.dev', 'x', 'n', 1)"))

        _alembic(url, "downgrade", PREVIOUS_HEAD)
        assert "ix_users_email_lower" not in _index_names(engine)
    finally:
        engine.dispose()


# --- review follow-ups (2026-11-21) -------------------------------------------

def test_seed_demo_finds_a_case_variant_demo_row_instead_of_inserting(db, monkeypatch):
    """With the lower(email) index, an exact-match demo lookup that misses
    `Demo@finly.app` would INSERT `demo@finly.app`, hit the index, and 500 the
    demo login. The lookup follows the F64 rule, so it reuses the existing row."""
    from app.core.config import settings
    from app.services.demo_seed import get_demo_user, seed_demo

    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "demo@finly.app")
    _raw_user(db, "Demo@finly.app")
    existing_id = db.query(User).one().id

    assert get_demo_user(db).id == existing_id
    assert seed_demo(db).id == existing_id
    assert db.query(User).count() == 1


def test_demo_login_with_a_case_variant_demo_row(client, db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "demo@finly.app")
    _raw_user(db, "DEMO@finly.app")
    assert client.post("/api/v1/auth/demo-login").status_code == 200
    assert db.query(User).count() == 1


def test_a_mixed_case_demo_email_setting_is_stored_normalised(db, monkeypatch):
    from app.core.config import settings
    from app.services.demo_seed import get_demo_user, seed_demo

    monkeypatch.setattr(settings, "DEMO_USER_EMAIL", " Demo@Finly.app ")
    user = seed_demo(db)
    assert user.email == "demo@finly.app"
    assert get_demo_user(db).id == user.id


def test_a_refused_registration_logs_the_constraint_but_no_secrets(client, db, monkeypatch, caplog):
    """The broad `except IntegrityError` must not hide WHICH constraint fired, and
    the log must carry neither the password nor its hash (str(IntegrityError)
    would include the INSERT's parameters, so only the driver's first line is logged)."""
    _raw_user(db, "Logged@finly.dev")
    monkeypatch.setattr(auth_module, "find_user_by_email", lambda *a: None)
    with caplog.at_level("WARNING", logger="app.services.auth"):
        res = _register(client, "logged@finly.dev", password="sekrit-pass-99")
    assert res.status_code == 400
    messages = [r.getMessage() for r in caplog.records if r.name == "app.services.auth"]
    assert len(messages) == 1, messages
    assert "ix_users_email_lower" in messages[0]
    assert "sekrit-pass-99" not in messages[0]
    assert "$2b$" not in messages[0]  # no bcrypt hash
