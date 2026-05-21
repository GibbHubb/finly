from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./finly.db"
    SECRET_KEY: str = "dev-secret-change-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    # E2E_MODE — when truthy, the /test/* utility endpoints are exposed.
    # Must be off in production. Set via env var E2E_MODE=1 for Playwright runs.
    E2E_MODE: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
