import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.ws import router as ws_router
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

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

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health", tags=["health"])
def health():
    logger.info("Health check requested")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# F27 — Nightly bank-sync scheduler (APScheduler, in-process). No-ops when
# GoCardless creds aren't configured, so dev still boots cleanly.
# ---------------------------------------------------------------------------
@app.on_event("startup")
def _start_bank_sync_scheduler():
    from app.core.config import settings as _settings
    if not (_settings.GOCARDLESS_SECRET_ID and _settings.GOCARDLESS_SECRET_KEY):
        logger.info("F27 scheduler: GoCardless creds not set, nightly sync disabled")
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("F27 scheduler: apscheduler not installed; pip install apscheduler")
        return
    from app.db.session import SessionLocal
    from app.services.bank_sync_service import sync_all_active

    def _job():
        db = SessionLocal()
        try:
            res = sync_all_active(db)
            logger.info("F27 nightly sync: %s", res)
        except Exception as exc:  # never let the job crash the scheduler
            logger.exception("F27 nightly sync failed: %s", exc)
        finally:
            db.close()

    sched = BackgroundScheduler()
    sched.add_job(_job, "interval", hours=_settings.SYNC_INTERVAL_HOURS, id="bank_sync")
    sched.start()
    app.state.bank_sync_scheduler = sched
    logger.info("F27 scheduler: nightly bank sync every %sh", _settings.SYNC_INTERVAL_HOURS)


@app.on_event("shutdown")
def _stop_bank_sync_scheduler():
    sched = getattr(app.state, "bank_sync_scheduler", None)
    if sched:
        sched.shutdown(wait=False)


# ---------------------------------------------------------------------------
# F33 — public demo account: seed on boot, then reset on an interval so a
# recruiter always finds a populated, un-trashed app. Entirely inert unless
# DEMO_MODE is on — the reset job DELETES rows, so it must never start by
# accident on a real deployment.
# ---------------------------------------------------------------------------
@app.on_event("startup")
def _start_demo_scheduler():
    from app.core.config import settings as _s
    if not _s.DEMO_MODE:
        return

    from app.db.session import SessionLocal
    from app.services.demo_seed import reset_demo, seed_demo

    db = SessionLocal()
    try:
        seed_demo(db)
    except Exception as exc:      # a failed seed must not stop the app booting
        logger.exception("F33: demo seed on startup failed: %s", exc)
    finally:
        db.close()

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("F33: apscheduler not installed; demo will not auto-reset")
        return

    def _job():
        db = SessionLocal()
        try:
            reset_demo(db)
        except Exception as exc:
            logger.exception("F33 demo reset failed: %s", exc)
        finally:
            db.close()

    sched = BackgroundScheduler()
    sched.add_job(_job, "interval", minutes=_s.DEMO_RESET_MINUTES, id="demo_reset")
    sched.start()
    app.state.demo_scheduler = sched
    logger.info("F33: demo mode on, resetting every %s min", _s.DEMO_RESET_MINUTES)


@app.on_event("shutdown")
def _stop_demo_scheduler():
    sched = getattr(app.state, "demo_scheduler", None)
    if sched:
        sched.shutdown(wait=False)
