from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str
    STORAGE_ROOT: str = "/data/photos"
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID: str = ""
    PUBLIC_BASE_URL: str = ""
    ADMIN_TOKEN: str = ""
    EVENT_ACCESS_SECRET: str = ""
    EVENT_ACCESS_TTL_HOURS: int = 12
    CELERY_CONCURRENCY: int = 2
    UVICORN_WORKERS: int = 2

    # ── Branding ──────────────────────────────────────────────────────────────
    SITE_NAME: str = "Race Photos"
    SITE_TAGLINE: str = "Your race, your photos."


settings = Settings()
