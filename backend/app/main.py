from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.ws import router as ws_router
from app.db.session import Base, engine
import app.models.user        # noqa: F401 — register models with SQLAlchemy
import app.models.transaction  # noqa: F401
import app.models.budget       # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Finly API",
    description="Personal Finance Tracker — REST API with JWT auth",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
