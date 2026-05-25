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

    class Config:
        env_file = ".env"


settings = Settings()
