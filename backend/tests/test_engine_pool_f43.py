"""F43 — the Postgres engine must not hold a connection pool inside a frozen serverless function."""
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool, QueuePool

from app.db.session import engine_kwargs


def test_postgres_url_gets_nullpool():
    url = "postgresql://u:p@db.example.invalid:5432/x"
    eng = create_engine(url, **engine_kwargs(url))  # no connection is made until first use
    assert isinstance(eng.pool, NullPool)


def test_sqlite_url_is_unchanged():
    kw = engine_kwargs("sqlite:///./test.db")
    assert kw == {"connect_args": {"check_same_thread": False}}


def test_the_default_would_have_pooled():  # control: without F43's kwargs, Postgres gets a QueuePool
    eng = create_engine("postgresql://u:p@db.example.invalid:5432/x")
    assert isinstance(eng.pool, QueuePool)
