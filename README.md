# 💸 Finly — Personal Finance Tracker

![Tests](https://github.com/GibbHubb/finly/actions/workflows/test.yml/badge.svg)

> Full-stack personal finance tracker built with **FastAPI** + **React**.  
> Demonstrates REST API design, JWT auth, SQL (SQLite → Postgres), and React hooks & state.

## Tech Stack

| Layer     | Technology                              |
|-----------|-----------------------------------------|
| Frontend  | React 18, TypeScript, Zustand, Recharts |
| Backend   | FastAPI, SQLAlchemy, Alembic, Pydantic  |
| Auth      | JWT (python-jose) + bcrypt              |
| DB        | SQLite (dev) / PostgreSQL (prod)        |
| CI        | GitHub Actions                          |

## Quick Start

```bash
cp .env.example .env
# Fill in your values in .env
docker compose up
```

App runs at http://localhost:3000, API at http://localhost:8000.

---

## Getting Started (without Docker)

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Project Structure
```
finly/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # Route handlers
│   │   ├── core/               # Config, security, JWT
│   │   ├── db/                 # Database session
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   └── services/           # Business logic layer
│   ├── tests/
│   └── alembic/                # DB migrations
└── frontend/
    └── src/
        ├── components/         # Reusable UI components
        ├── hooks/              # Custom React hooks
        ├── pages/              # Route-level page components
        ├── services/           # API client functions
        ├── store/              # Zustand global state
        └── types/              # TypeScript interfaces
```

## Git Workflow

Branches: `main` → `develop` → `feature/*` / `fix/*` / `chore/*`

Commit convention (Conventional Commits):
```
feat(auth): add JWT refresh token endpoint
fix(transactions): correct negative balance calculation
chore(deps): bump fastapi to 0.111
```

## API Docs
FastAPI auto-generates interactive docs at:
- Swagger UI: http://localhost:8000/docs
- ReDoc:       http://localhost:8000/redoc

## End-to-end tests (Playwright)

The `frontend/e2e/` directory contains Playwright specs covering the four
core happy paths: login, add transaction, budget over-limit alert, savings
goal progress.

The suite spins up the FastAPI backend (with `E2E_MODE=1` exposing
`/api/v1/test/reset`) and the Vite dev server automatically via
`playwright.config.ts → webServer`.

First-time setup (downloads ~200 MB of browser binaries):
```bash
cd frontend
npm install
npm run e2e:install
```

Run the suite:
```bash
npm run e2e         # headless
npm run e2e:ui      # interactive Playwright UI mode
```

CI runs the same flow on every PR via `.github/workflows/e2e.yml`. Trace
files are uploaded as artifacts on failure (`frontend/test-results/`).
