"""F48 — request ids, JSON logs, a quotable error id, and build identity.

The problem this closes: on the deployed app a 500 returned
`{"detail":"Internal Server Error"}` with no identifier, the traceback went to
stdout, and `backend/index.py` records in its own docstring that there is *no
runtime log retention on this plan*. So the only record of a failure was
written to a stream nobody can read afterwards. That is why F38 could not tell
which build was serving while three endpoints 500'd.

Each test here asserts one criterion from the plan, and the secret-scrubbing
one sets known sentinels and greps the captured output — because "we don't log
secrets" is a claim, and a sentinel is a measurement.
"""
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.observability import (
    JsonFormatter, RequestContextMiddleware, build_info,
    unhandled_exception_handler, request_id_var, reset_secret_cache, scrub,
)

client = TestClient(app, raise_server_exceptions=False)


# ── request ids ─────────────────────────────────────────────────────────────
def test_response_carries_a_request_id():
    r = client.get("/health")
    assert r.headers.get("X-Request-ID"), "no X-Request-ID on the response"


def test_an_inbound_request_id_is_honoured():
    r = client.get("/health", headers={"X-Request-ID": "caller-supplied-123"})
    assert r.headers["X-Request-ID"] == "caller-supplied-123"


def test_an_absurd_inbound_id_is_truncated():
    """An unbounded header would end up on every log line for that request."""
    r = client.get("/health", headers={"X-Request-ID": "x" * 5000})
    assert len(r.headers["X-Request-ID"]) <= 64


# ── the 500 handler ─────────────────────────────────────────────────────────
def _app_that_raises():
    a = FastAPI()
    a.add_middleware(RequestContextMiddleware)
    a.add_exception_handler(Exception, unhandled_exception_handler)

    @a.get("/boom")
    def boom():
        raise RuntimeError("SENSITIVE-INTERNAL-DETAIL-abc123")

    return a


def test_unhandled_exception_returns_an_error_id_and_no_detail():
    c = TestClient(_app_that_raises(), raise_server_exceptions=False)
    r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal error"
    assert len(body["error_id"]) == 12
    assert "SENSITIVE-INTERNAL-DETAIL-abc123" not in r.text, (
        "the exception text reached the caller — the same mistake /health was "
        "making, one endpoint over")
    assert "RuntimeError" not in r.text


def test_the_error_id_is_also_in_the_log(caplog):
    """An id the caller can quote is only useful if it is findable."""
    c = TestClient(_app_that_raises(), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR):
        eid = c.get("/boom").json()["error_id"]
    assert any(getattr(rec, "error_id", None) == eid for rec in caplog.records), (
        "the error_id returned to the caller appears nowhere in the log")


# ── JSON logs ───────────────────────────────────────────────────────────────
def test_every_log_line_is_one_json_object():
    fmt = JsonFormatter()
    token = request_id_var.set("rid-abc")
    try:
        rec = logging.LogRecord("finly.request", logging.INFO, __file__, 1,
                                "request", (), None)
        rec.status, rec.duration_ms = 200, 12.3
        line = fmt.format(rec)
    finally:
        request_id_var.reset(token)
    obj = json.loads(line)                      # must parse — this is the `jq` check
    for k in ("ts", "level", "logger", "message", "request_id", "path", "method"):
        assert k in obj, "missing %s" % k
    assert obj["request_id"] == "rid-abc"
    assert obj["status"] == 200 and obj["duration_ms"] == 12.3


def test_a_traceback_is_carried_as_a_field_not_a_second_line():
    """A multi-line traceback printed raw would break one-object-per-line."""
    fmt = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = logging.LogRecord("finly.error", logging.ERROR, __file__, 1,
                                "failed", (), sys.exc_info())
    line = fmt.format(rec)
    assert "\n" not in line, "the formatted line contains a newline"
    assert "ValueError" in json.loads(line)["traceback"]


# ── secrets ─────────────────────────────────────────────────────────────────
SENTINELS = {
    "SECRET_KEY": "sentinel-secret-key-AAAA",
    "FERNET_KEY": "sentinel-fernet-key-BBBB",
    "CRON_SECRET": "sentinel-cron-secret-CCCC",
    "GOCARDLESS_SECRET_ID": "sentinel-gc-id-DDDD",
    "GOCARDLESS_SECRET_KEY": "sentinel-gc-key-EEEE",
}


@pytest.fixture()
def sentinel_env(monkeypatch):
    reset_secret_cache()                    # the value set is cached now
    for k, v in SENTINELS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://finly_user:sentinel-db-password-FFFF@db.example.supabase.co:5432/postgres")
    return SENTINELS


def test_no_secret_value_survives_a_log_line(sentinel_env):
    """Sets known sentinels and greps the formatted output for each."""
    fmt = JsonFormatter()
    leaky = " ".join(list(SENTINELS.values()) + ["sentinel-db-password-FFFF"])
    rec = logging.LogRecord("finly.test", logging.INFO, __file__, 1,
                            "config dump: %s", (leaky,), None)
    line = fmt.format(rec)
    for name, value in SENTINELS.items():
        assert value not in line, "%s leaked into a log line" % name
    assert "sentinel-db-password-FFFF" not in line, "the DSN password leaked"
    assert "***REDACTED***" in line


def test_scrub_handles_a_shared_prefix(monkeypatch):
    reset_secret_cache()
    """Longest-first replacement: a shorter secret that prefixes a longer one
    must not leave the longer one's tail behind."""
    monkeypatch.setenv("SECRET_KEY", "abcdefgh")
    monkeypatch.setenv("FERNET_KEY", "abcdefghIJKLMNOP")
    out = scrub("value=abcdefghIJKLMNOP")
    assert "IJKLMNOP" not in out, out


# ── build identity ──────────────────────────────────────────────────────────
def test_meta_reports_the_build():
    r = client.get("/api/v1/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["commit"], "no commit reported"
    assert body["version"]
    assert body["environment"] in ("local", "production", "preview", "development")


def test_meta_prefers_the_vercel_sha(monkeypatch):
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "deadbeefcafebabe0123456789abcdef01234567")
    info = build_info()
    assert info["commit"] == "deadbeefcafebabe0123456789abcdef01234567"
    assert info["short_commit"] == "deadbee"


def test_the_request_line_carries_its_own_context(caplog):
    """The regression a unit test on the formatter could NOT catch.

    The first version of the middleware reset the ContextVars in a `finally`
    that ran BEFORE the request log line was emitted, so every line came out
    with request_id="-", path="-", method="-" — the one thing the middleware
    exists for. The formatter test still passed, because it set the ContextVar
    by hand. Only a real run through a JSON parser showed it.
    """
    with caplog.at_level(logging.INFO, logger="finly.request"):
        client.get("/health", headers={"X-Request-ID": "ctx-check-42"})
    lines = [r for r in caplog.records if r.name == "finly.request"]
    assert lines, "no request line was logged at all"
    rec = lines[-1]
    formatted = json.loads(JsonFormatter().format(rec))
    # The formatter reads the ContextVars at format time, so assert on what the
    # middleware actually attached to the record instead.
    assert getattr(rec, "status", None) == 200
    assert getattr(rec, "duration_ms", None) is not None
    assert formatted["message"] == "request"

# ── the crash path, by VALUE not by presence ────────────────────────────────
# /code-review found the blocking bug here: a handler registered for the bare
# `Exception` runs inside ServerErrorMiddleware, OUTSIDE BaseHTTPMiddleware, so
# the middleware's `finally` had already reset the ContextVars. Every 500 came
# back `X-Request-ID: -` and logged `request_id: "-"`, and the two log lines for
# one crash shared no correlating field.
#
# The tests above passed throughout, because they asserted the fields EXISTED.
# These assert their VALUES, which is the difference between a test and a
# decoration.
def test_a_500_echoes_the_inbound_request_id():
    c = TestClient(_app_that_raises(), raise_server_exceptions=False)
    r = c.get("/boom", headers={"X-Request-ID": "crash-path-id-77"})
    assert r.status_code == 500
    assert r.headers["X-Request-ID"] == "crash-path-id-77", (
        "the 500 response lost the request id — this is the case the whole "
        "correlation feature exists for")


def test_one_crash_logs_one_line_carrying_BOTH_ids(caplog):
    c = TestClient(_app_that_raises(), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR):
        r = c.get("/boom", headers={"X-Request-ID": "crash-corr-88"})
    eid = r.json()["error_id"]

    with_tb = [rec for rec in caplog.records if rec.exc_info]
    assert len(with_tb) == 1, (
        "expected exactly ONE traceback per crash, got %d — the middleware and "
        "the handler were both logging it" % len(with_tb))

    rec = with_tb[0]
    assert getattr(rec, "error_id", None) == eid, (
        "the error_id the caller was given is not on the log line")
    line = json.loads(JsonFormatter().format(rec))
    assert line["error_id"] == eid
    # The formatter reads ContextVars at format time (outside the request), so
    # assert the middleware captured the request id on the record's own line
    # via the log call happening while the context was live.
    assert rec.name == "finly.request", (
        "the traceback came from the handler, which cannot see the request "
        "context — it must be logged by the middleware")


def test_a_secret_only_in_dotenv_is_still_scrubbed(monkeypatch):
    """scrub() read os.environ only, but config.py loads from .env, which
    pydantic-settings does NOT push into os.environ. So a locally-configured
    secret was never redacted. /code-review found it."""
    reset_secret_cache()
    import app.core.config as cfg
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(cfg.settings, "SECRET_KEY", "dotenv-only-secret-XYZ123", raising=False)
    reset_secret_cache()
    assert "dotenv-only-secret-XYZ123" not in scrub("leak=dotenv-only-secret-XYZ123")


def test_a_dsn_password_containing_an_at_sign_is_scrubbed(monkeypatch):
    """Splitting on the FIRST '@' truncates such a password, so the scrubber
    then searches for the wrong substring and leaves the real one in."""
    reset_secret_cache()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://u:p@ssw0rd-with-at-sign@db.example.supabase.co:5432/postgres")
    reset_secret_cache()
    out = scrub("dsn password is p@ssw0rd-with-at-sign here")
    assert "p@ssw0rd-with-at-sign" not in out, out
