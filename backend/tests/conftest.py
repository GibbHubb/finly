"""Shared fixtures.

F45 — the same suite runs on SQLite (default, every commit) or on a real Postgres.

  * SQLite: `Base.metadata.create_all` / `drop_all` per test, exactly as before (fast).
  * Postgres: set TEST_DATABASE_URL. The schema is built ONCE per session by
    `alembic upgrade head` — so the suite exercises the migrated schema, not the models'
    idea of it — and every table is truncated after each test.

TEST_DATABASE_URL is deliberately NOT DATABASE_URL: this fixture truncates every table, so
a variable that is also "where the app's real data lives" must never be able to steer it.
And it refuses any Postgres host that is not local or the CI service container, because
finly's real database is a Supabase project it shares with three other apps.
"""
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app

TEST_DB = os.environ.get("TEST_DATABASE_URL") or "sqlite:///./test.db"
IS_POSTGRES = TEST_DB.startswith("postgresql")

# Hosts a test run may truncate: a local container, or the CI service container.
_SAFE_PG_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres"}

if IS_POSTGRES:
    _host = urlparse(TEST_DB).hostname
    if _host not in _SAFE_PG_HOSTS:
        raise pytest.UsageError(
            f"TEST_DATABASE_URL points at {_host!r}. The suite TRUNCATES every table, so it "
            f"only runs against a throwaway Postgres on {sorted(_SAFE_PG_HOSTS)}."
        )
    engine = create_engine(TEST_DB)
else:
    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})

TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _alembic_upgrade_head() -> None:
    from alembic import command
    from alembic.config import Config

    # No ini file on purpose: alembic/env.py calls logging.config.fileConfig() whenever the
    # Config has one, and fileConfig DISABLES every logger that already exists — the app's
    # included — so every caplog assertion after this point saw nothing (first Postgres run).
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    # alembic/env.py reads DATABASE_URL, so point it at the test database for this call only.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DB
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema():
    if IS_POSTGRES:
        _alembic_upgrade_head()
    yield


def _truncate_all() -> None:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        # A test that leaves a transaction open would otherwise make TRUNCATE wait for its
        # lock forever: a hung CI job instead of a failed one.
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def setup_db():
    if IS_POSTGRES:
        yield
        _truncate_all()
        return
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
