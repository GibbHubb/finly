from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def engine_kwargs(url: str) -> dict:
    """F43 — the engine options for this URL.

    SQLite (tests, local): unchanged.

    Postgres (the Vercel function): NullPool. SQLAlchemy's default QueuePool keeps up to 15
    connections per process open, and a Vercel function is frozen between requests and runs in
    many containers at once, so those idle connections pile up against a Supabase project that
    finly SHARES with Our_Menu, Poly_Tracker and Cortana: a slot finly holds idle is one those
    apps cannot get. NullPool opens one connection per request and closes it after, the same
    choice alembic/env.py already makes. pool_pre_ping is not needed with NullPool: a
    connection is never reused, so it can never be a stale one left over from a freeze.
    """
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"poolclass": NullPool}


engine = create_engine(settings.DATABASE_URL, **engine_kwargs(settings.DATABASE_URL))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
