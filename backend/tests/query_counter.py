"""F44 — count SQL statements, so a query budget is asserted in CI instead of measured once."""
from contextlib import contextmanager

from sqlalchemy import event


@contextmanager
def count_queries(engine):
    """Yields a list that fills with one entry per SQL statement executed on `engine`."""
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", before)


@contextmanager
def assert_max_queries(engine, n):
    with count_queries(engine) as seen:
        yield seen
    assert len(seen) <= n, f"{len(seen)} statements, budget {n}:\n" + "\n---\n".join(s[:160] for s in seen)
