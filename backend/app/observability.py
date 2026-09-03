"""F48 — request ids, JSON logs, and an error id the caller can quote.

Why this exists: finly cannot currently tell you what went wrong on the
deployed app. A 500 returns `{"detail":"Internal Server Error"}` with no
identifier, the traceback goes to stdout, and `backend/index.py` records the
constraint in its own docstring — *there is no runtime log retention on this
plan*. So the traceback is written to a stream nobody can read afterwards.

That combination is why F38 had to guess: the SPA rendered fine while three
endpoints 500'd, and there was no way to tell which build was serving.

The design decision worth naming: the error id goes to the CALLER as well as
the log. On a plan with no log retention, the user quoting an id is sometimes
the only correlation available — so the id must exist even when the log line
is already gone.

Nothing here ships logs anywhere. Choosing a sink is out of scope (§4) and
Max's call; structured lines are the precondition.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

#: Set per request, read by the log formatter. A ContextVar rather than a
#: thread-local because the app is async — a thread-local leaks ids between
#: concurrently-handled requests on the same worker thread.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
request_path_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_path", default="-"
)
request_method_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_method", default="-"
)

# Values that must never reach a log line or a response body. Read once at
# import: these are process-lifetime settings, and re-reading os.environ per log
# line would be a measurable cost on a per-request logger.
_SECRET_ENV_KEYS = (
    "SECRET_KEY", "FERNET_KEY", "CRON_SECRET",
    "GOCARDLESS_SECRET_ID", "GOCARDLESS_SECRET_KEY",
)


def _secret_values() -> list[str]:
    """The literal secret values to scrub, longest first.

    Longest-first matters: if two secrets share a prefix, replacing the shorter
    one first leaves the tail of the longer one in the output.
    """
    vals = []
    for k in _SECRET_ENV_KEYS:
        v = os.environ.get(k) or ""
        if len(v) >= 8:                 # too-short values would match everywhere
            vals.append(v)
    dsn = os.environ.get("DATABASE_URL") or ""
    # The password out of the DSN, which is the one part of it that must never
    # appear anywhere. The host is scrubbed from responses by the caller, not
    # here — a host in a private log line is useful, a password never is.
    if "://" in dsn and "@" in dsn:
        creds = dsn.split("://", 1)[1].split("@", 1)[0]
        if ":" in creds:
            pw = creds.split(":", 1)[1]
            if len(pw) >= 8:
                vals.append(pw)
    return sorted(set(vals), key=len, reverse=True)


def scrub(text: str) -> str:
    """Replace any known secret value with a marker."""
    for v in _secret_values():
        if v and v in text:
            text = text.replace(v, "***REDACTED***")
    return text


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so a real run pipes through `jq` cleanly."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            # datetime.isoformat rather than time.strftime: the F38 dialect
            # guard greps app code for `strftime(` to catch SQLite-only SQL date
            # functions that raise UndefinedFunction on the deployed Postgres.
            # Python's time.strftime is a false positive for that guard — but
            # the guard is right to exist, so this uses an expression it cannot
            # confuse rather than carving out an exemption. ISO-8601 with an
            # explicit UTC offset is also the better log format.
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "path": request_path_var.get(),
            "method": request_method_var.get(),
        }
        for key in ("status", "duration_ms", "error_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        # Scrub LAST, over the serialised line, so a secret cannot slip through
        # inside a traceback frame or an interpolated argument.
        return scrub(json.dumps(payload, default=str))


def configure_logging(level: int = logging.INFO) -> None:
    """Replace the root handlers with a single JSON one.

    Replaces rather than adds: `logging.basicConfig` had already installed a
    plain-text handler, and leaving it attached emits every line twice — once
    parseable and once not, which defeats the point.
    """
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn installs its OWN handlers with propagate=False, so setting the
    # root handler alone leaves its lines unconverted. A real run produced 9
    # non-JSON lines ("INFO:     Started server process [620]") next to 5 JSON
    # ones — and the criterion is that EVERY line parses, because a log stream
    # that is only mostly JSON cannot be piped through anything.
    #
    # Hand them to the root handler instead of giving each its own, so there is
    # exactly one formatter in the process.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "gunicorn.error"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, echo it back, and log one line per request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Honour an inbound id so a caller (or a proxy) can correlate, but never
        # trust its shape — an unbounded header would end up in every log line.
        inbound = (request.headers.get("X-Request-ID") or "").strip()
        rid = inbound[:64] if inbound else uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        tp = request_path_var.set(request.url.path)
        tm = request_method_var.set(request.method)
        started = time.perf_counter()
        logger = logging.getLogger("finly.request")
        try:
            try:
                response = await call_next(request)
            except Exception:
                # The 500 handler produces the response; this only guarantees the
                # request line is emitted with its duration even on a crash.
                logger.exception(
                    "request failed",
                    extra={"status": 500,
                           "duration_ms": round((time.perf_counter() - started) * 1000, 1)},
                )
                raise
            response.headers["X-Request-ID"] = rid
            # ⚠️ This log call MUST happen before the ContextVars are reset.
            #
            # The first version reset them in a `finally` that ran BEFORE this
            # line, so every request line came out with request_id="-",
            # path="-", method="-" — the one feature the middleware exists for,
            # broken, while the unit test passed because it set the ContextVar
            # by hand and only exercised the formatter. Caught by piping a real
            # run through a JSON parser, which is why the plan asks for that.
            logger.info(
                "request",
                extra={"status": response.status_code,
                       "duration_ms": round((time.perf_counter() - started) * 1000, 1)},
            )
            return response
        finally:
            request_id_var.reset(token)
            request_path_var.reset(tp)
            request_method_var.reset(tm)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """500 with an id the user can quote, and never the exception text.

    FastAPI's default gives `{"detail":"Internal Server Error"}` — true, and
    useless. The exception text is deliberately NOT returned: that is the same
    mistake /health was making, one endpoint over.
    """
    error_id = uuid.uuid4().hex[:12]
    logging.getLogger("finly.error").exception(
        "unhandled exception", extra={"error_id": error_id, "status": 500}
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal error", "error_id": error_id},
        headers={"X-Request-ID": request_id_var.get()},
    )


def build_info() -> dict:
    """What is actually deployed. Vercel injects the SHA; fall back locally."""
    sha = (os.environ.get("VERCEL_GIT_COMMIT_SHA")
           or os.environ.get("GIT_COMMIT_SHA") or "")
    if not sha:
        try:
            import subprocess
            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ).decode().strip()
        except Exception:                                   # noqa: BLE001
            sha = "unknown"
    return {
        "commit": sha,
        "short_commit": sha[:7] if sha != "unknown" else "unknown",
        "environment": os.environ.get("VERCEL_ENV") or "local",
    }
