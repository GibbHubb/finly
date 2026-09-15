"""F38 — the test suite runs on SQLite, production runs on Postgres.

Three endpoints (`/transactions/summary`, `/transactions/trends` and the
year-in-review PDF) shipped using `func.strftime(...)`, which exists only in
SQLite. Every test stayed green while all three returned 500 on the deployed
app for months, because nothing in CI ever spoke to Postgres.

Until the suite runs against Postgres, this is the cheap mechanical guard: a
SQLite-only date function must not appear in application code at all.
"""
import os
import re

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")

# SQLite-only, with no Postgres equivalent of the same name.
SQLITE_ONLY = re.compile(r"\bfunc\.(strftime|julianday|unixepoch|datetime|date|time)\s*\(")

# The same functions written as raw SQL — inside text(), an execute() string or
# an f-string. `func.` is the shape that caused F38, but raw SQL reaches the
# database the same way and fails identically on Postgres.
RAW_SQLITE_ONLY = re.compile(r"\b(strftime|julianday|unixepoch)\s*\(", re.I)

# `#` comments are prose, not SQL — an entry in this file's own docstring must
# not fail CI (a guard that cries wolf gets deleted, which is F-NOISYGUARD).
COMMENT = re.compile(r"^\s*#")


def _python_sources():
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def _scan(sources):
    offenders = []
    for path in sources:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if COMMENT.match(line):
                    continue
                m = SQLITE_ONLY.search(line)
                if m:
                    offenders.append(f"{os.path.relpath(path, APP_DIR)}:{lineno} "
                                     f"uses func.{m.group(1)}()")
                    continue
                m = RAW_SQLITE_ONLY.search(line)
                if m:
                    offenders.append(f"{os.path.relpath(path, APP_DIR)}:{lineno} "
                                     f"uses raw SQL {m.group(1)}()")
    return offenders


def test_no_sqlite_only_date_functions_in_app_code():
    offenders = _scan(_python_sources())
    assert not offenders, (
        "SQLite-only date function(s) in application code — these raise "
        "UndefinedFunction on the deployed Postgres while this suite stays "
        "green (F38). Use sqlalchemy.extract() instead:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_itself_fires_on_a_known_bad_file(tmp_path):
    """BB18 — a check that has never gone red is indistinguishable from one
    that cannot. Feed the scanner the exact code F38 removed and require it to
    complain; feed it the portable replacement and require silence."""
    bad = tmp_path / "bad_service.py"
    bad.write_text(
        "from sqlalchemy import func\n"
        "q.filter(func.strftime('%Y', Transaction.transaction_date) == '2026')\n",
        encoding="utf-8",
    )
    raw = tmp_path / "raw_service.py"
    raw.write_text("db.execute(text(\"select julianday('now')\"))\n", encoding="utf-8")
    good = tmp_path / "good_service.py"
    good.write_text(
        "from sqlalchemy import extract\n"
        "q.filter(extract('year', Transaction.transaction_date) == 2026)\n",
        encoding="utf-8",
    )
    commented = tmp_path / "commented_service.py"
    commented.write_text("# this used to call func.strftime('%Y', col)\n", encoding="utf-8")

    assert _scan([bad]), "the guard did not flag func.strftime — it cannot fail"
    assert _scan([raw]), "the guard did not flag raw julianday() in text()"
    assert not _scan([good]), "the guard flagged the portable extract() form"
    assert not _scan([commented]), "the guard flagged a comment, not code"
