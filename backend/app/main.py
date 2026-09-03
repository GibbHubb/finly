import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.db.session import Base, engine
import app.models.user           # noqa: F401 — register models with SQLAlchemy
import app.models.transaction    # noqa: F401
import app.models.budget         # noqa: F401
import app.models.savings_goal   # noqa: F401
import app.models.import_mapping # noqa: F401
import app.models.categorisation_rule # noqa: F401
import app.models.fx_rate         # noqa: F401
import app.models.bank_connection  # noqa: F401  — F27
import app.models.tag               # noqa: F401  — F29

# F48 — one JSON object per line, so a real run pipes through `jq`. This
# REPLACES the root handlers rather than adding one: basicConfig's plain-text
# handler would otherwise emit every line twice, once parseable and once not.
from app.observability import (  # noqa: E402
    RequestContextMiddleware, build_info, configure_logging,
    unhandled_exception_handler,
)

configure_logging(logging.INFO)
logger = logging.getLogger(__name__)

# F34 — `Base.metadata.create_all(bind=engine)` was here.
#
# It did schema DDL round trips on every import — which on a serverless host is
# every cold start — and it meant Alembic was not actually the source of truth.
# It was also covering for a broken migration history: the chain had a DUPLICATE
# revision id and a cycle, so `alembic upgrade head` could not run at all, and
# nobody noticed because create_all quietly built the schema anyway.
#
# The history is repaired and squashed to one baseline. `alembic upgrade head`
# is the only thing that creates tables now.

app = FastAPI(
    title="Finly API",
    description="Personal Finance Tracker — REST API with JWT auth",
    version="0.1.0",
)

# F33 — origins come from settings so the deployed static site can call the
# API. Was hardcoded to the Vite dev server, which made the app unusable from
# any other origin.
from app.core.config import settings as _settings  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# F48 — request id in, request id out, one log line per request. Added AFTER
# CORS so the id header survives the CORS response wrapping.
app.add_middleware(RequestContextMiddleware)

# F48 — an unhandled exception must return an id the user can quote, not
# `{"detail":"Internal Server Error"}`. `backend/index.py` records that this
# plan has no log retention, so the id in the caller's hand is sometimes the
# only correlation that still exists.
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.get("/api/v1/meta", tags=["meta"])
def meta():
    """Which build is serving. F38 had to answer this by clicking around."""
    return {"version": app.version, **build_info()}


app.include_router(api_router)
# F34 — the WebSocket router (`/ws/transactions`) is gone. Vercel's serverless
# functions cannot hold a socket open, so it could only ever have been a
# connection that fails and retries forever. It was already broken on Render:
# `VITE_WS_URL` was never set there, so the deployed SPA dialled
# `ws://localhost:8000` — the user's own machine. The transactions view polls
# instead (see useTransactionPolling.ts).


@app.get("/health", tags=["health"])
def health():
    """F34 — report the DATABASE, not a constant.

    This returned `{"status": "ok"}` unconditionally. That is the same defect
    Poly_Tracker shipped (PT22, where a DELETED database read as healthy for
    days) and repurpose shipped again (RP15) — a check that cannot fail tells
    you nothing, and it is worst precisely when something is wrong.
    """
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "up"}
    except Exception as exc:  # noqa: BLE001 — any failure to reach the DB counts
        # F48 — this used to return `str(exc)[:200]` to the caller, and /health
        # is unauthenticated and publicly routed (vercel.json:22).
        #
        # Measured 2026-09-03 with a deliberately fake DSN: on a DNS failure the
        # 200 characters contained the database HOST verbatim —
        #   (psycopg2.OperationalError) could not translate host name
        #   "db.<project-ref>.supabase.co" to address: ...
        # i.e. the Supabase project ref, handed to anyone who curls the endpoint.
        # The USER appears in the auth-failure shape ("password authentication
        # failed for user ..."), which is server-generated and was not
        # reproduced here. The PASSWORD does NOT appear in psycopg2 error text —
        # so this is information disclosure, not credential disclosure, and the
        # earlier note claiming the password leaked was wrong.
        #
        # The endpoint must still be ABLE to fail (F34 added it because a health
        # check that cannot fail tells you nothing — PT22/RP15). So it keeps the
        # 503; what changes is that the detail goes to the log under an id, and
        # the caller gets only the id.
        error_id = uuid.uuid4().hex[:12]
        logger.exception("Health check: database unreachable [error_id=%s]", error_id)
        return JSONResponse(
            status_code=503,
            content={"status": "error", "db": "down", "error_id": error_id},
        )


# ---------------------------------------------------------------------------
# F34 — the two in-process schedulers are gone, and are cron-callable endpoints.
#
# There were TWO `BackgroundScheduler`s started on `@app.on_event("startup")`:
# the nightly bank sync (F27) and the demo reset (F33). A serverless function is
# invoked per request and frozen in between, so neither would ever have fired —
# and, worse, neither would have SAID so. The app would deploy, return 200 to
# everything, and silently never sync or reset. That is the exact failure RP14
# was filed for on a different project.
#
# As endpoints, a run leaves an HTTP status and a log line, and the caller is
# Vercel Cron (see vercel.json). Both refuse without the shared secret, because
# `demo-reset` DELETES rows.
#
# ⚠️ They answer GET as well as POST because **Vercel Cron issues a GET**, and a
# POST-only task endpoint would have returned 405 to every scheduled run — a
# scheduler that fires and achieves nothing, which is the failure this whole
# change exists to remove.
#
# ⚠️ The demo resets DAILY, not hourly. Vercel's Hobby plan allows two cron jobs
# per project at once-a-day frequency, so `DEMO_RESET_MINUTES = 60` can no longer
# be honoured by a schedule. The startup seed still runs on every cold start, so
# a fresh deployment is always populated; what changes is how quickly a visitor's
# edits are cleaned up after.
# ---------------------------------------------------------------------------
def _require_cron_secret(request: Request) -> None:
    from app.core.config import settings as _s

    secret = getattr(_s, "CRON_SECRET", "") or ""
    if not secret:
        # Refuse rather than run unauthenticated. The demo reset deletes rows;
        # an unset secret must fail closed, the PT23 way, not open.
        raise HTTPException(
            status_code=503,
            detail="CRON_SECRET is not configured on this deployment.",
        )
    sent = request.headers.get("authorization", "")
    if sent != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.api_route("/api/v1/tasks/bank-sync", methods=["GET", "POST"], tags=["tasks"])
def task_bank_sync(request: Request):
    """One pass of the nightly bank sync. Returns what it did, so a cron run
    that syncs nothing is distinguishable from one that did not happen."""
    _require_cron_secret(request)
    from app.core.config import settings as _s

    if not (_s.GOCARDLESS_SECRET_ID and _s.GOCARDLESS_SECRET_KEY):
        logger.info("F34 bank-sync: GoCardless creds not set, nothing to do")
        return {"ran": True, "synced": 0, "skipped": "no GoCardless credentials"}

    from app.db.session import SessionLocal
    from app.services.bank_sync_service import sync_all_active

    db = SessionLocal()
    try:
        res = sync_all_active(db)
        logger.info("F34 bank-sync: %s", res)
        return {"ran": True, "result": res}
    finally:
        db.close()


@app.api_route("/api/v1/tasks/demo-reset", methods=["GET", "POST"], tags=["tasks"])
def task_demo_reset(request: Request):
    """Reset the public demo account. Inert unless DEMO_MODE is on — it DELETES
    rows, so it must never run by accident on a real deployment."""
    _require_cron_secret(request)
    from app.core.config import settings as _s

    if not _s.DEMO_MODE:
        return {"ran": False, "reason": "DEMO_MODE is off"}

    from app.db.session import SessionLocal
    from app.services.demo_seed import reset_demo

    db = SessionLocal()
    try:
        reset_demo(db)
        logger.info("F34 demo-reset: demo account reset")
        return {"ran": True}
    finally:
        db.close()


@app.on_event("startup")
def _seed_demo_on_boot():
    """F33's seed is kept — it is idempotent and it is what makes a fresh
    deployment show a populated app rather than an empty one. Only the RESET
    half moved to cron, because that is the half that needs a clock."""
    from app.core.config import settings as _s
    if not _s.DEMO_MODE:
        return

    from app.db.session import SessionLocal
    from app.services.demo_seed import seed_demo

    db = SessionLocal()
    try:
        seed_demo(db)
    except Exception as exc:      # a failed seed must not stop the app booting
        logger.exception("F33: demo seed on startup failed: %s", exc)
    finally:
        db.close()
