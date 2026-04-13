# finly — Prod Readiness

Stack: FastAPI · SQLAlchemy · Alembic · Pydantic · JWT · React 18 · TS · Zustand

## Tasks (ordered — do 1/day)

### 1. Typed end-to-end test suite (backend + frontend)
Showcase: **pytest + httpx async client**, **factory-boy** fixtures, **Vitest + React Testing Library**, **MSW** for API mocking. Target: 80%+ coverage on `services/` and `store/`. Add coverage badge to README.
- Add `tests/` with `conftest.py` spinning up an in-memory SQLite + Alembic migration fixture
- Auth flow, budget CRUD, spend-vs-limit edge cases (over-budget, zero-budget, month rollover)
- `npm run test:ci` + `pytest --cov` wired into a single command

### 2. Security & auth hardening
Showcase: understanding of real-world auth threats.
- Move JWT secret to env-only, rotate on startup if dev default detected
- Add refresh-token rotation with reuse detection (revocation list in DB)
- Rate-limit `/auth/*` with `slowapi`
- Strict Pydantic v2 models on every request, `response_model` on every route
- Add `bandit` + `pip-audit` + `npm audit --production` to CI, fail on high severity

### 3. GitHub Actions CI + preview deploys
Showcase: modern DevOps.
- Matrix build (py 3.11/3.12, node 20)
- Ruff + mypy strict + eslint + tsc --noEmit
- Build Docker image, push to GHCR on `main`
- Preview deploy per PR (Fly.io or Railway) with ephemeral Postgres
- Release-please for semver tags + changelog
