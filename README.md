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
