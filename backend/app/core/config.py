from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./finly.db"
    SECRET_KEY: str = "dev-secret-change-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # E2E_MODE — when truthy, the /test/* utility endpoints are exposed.
    # Must be off in production. Set via env var E2E_MODE=1 for Playwright runs.
    E2E_MODE: bool = False

    # F27 — GoCardless Bank Account Data (sandbox). Empty defaults so the
    # app still boots without keys; the /bank/* endpoints will reject with
    # a 503 until the user sets these.
    GOCARDLESS_SECRET_ID: str = ""
    GOCARDLESS_SECRET_KEY: str = ""
    GOCARDLESS_BASE_URL: str = "https://bankaccountdata.gocardless.com/api/v2"
    GOCARDLESS_REDIRECT_URL: str = "http://localhost:5173/bank/callback"
    GOCARDLESS_SANDBOX_INSTITUTION: str = "SANDBOXFINANCE_SFIN0000"
    SYNC_INTERVAL_HOURS: int = 24

    # F31 — Fernet symmetric encryption key for at-rest secrets.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Leave empty in dev; the crypto helper raises loudly if encrypt/decrypt is
    # actually called without a key (it never silently writes plaintext).
    FERNET_KEY: str = ""

    # F33 — public demo deploy.
    # CORS origins are comma-separated so a single env var covers the deployed
    # static site plus local dev. Previously hardcoded to the Vite dev server,
    # which made the app unusable from any other origin.
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # DEMO_MODE gates the whole demo surface: the /auth/demo-login endpoint,
    # the startup seed, and the periodic reset job. Off by default so a real
    # deployment can never accidentally expose a passwordless login or run a
    # job that deletes rows.
    DEMO_MODE: bool = False
    DEMO_USER_EMAIL: str = "demo@finly.app"
    DEMO_USER_PASSWORD: str = "demo-only-not-a-secret"
    DEMO_USER_NAME: str = "Demo User"
    # How often the demo account is wiped back to the seeded baseline.
    DEMO_RESET_MINUTES: int = 60

    # F34 — the shared secret Vercel Cron sends. The scheduled tasks refuse
    # without it rather than running unauthenticated: `demo-reset` DELETES rows,
    # and a forgotten dashboard field must not be the difference between
    # "scheduled" and "anyone can wipe the demo".
    CRON_SECRET: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
