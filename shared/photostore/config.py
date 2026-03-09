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
    ADMIN_SESSION_SECRET: str = ""
    ADMIN_SESSION_TTL_MINUTES: int = 30
    ADMIN_REFRESH_TTL_HOURS: int = 12
    EVENT_ACCESS_TTL_HOURS: int = 12
    ORDER_ACCESS_TTL_HOURS: int = 720
    MAX_PHOTO_UPLOAD_BYTES: int = 100 * 1024 * 1024
    CELERY_CONCURRENCY: int = 2
    UVICORN_WORKERS: int = 2

    # ── Branding ──────────────────────────────────────────────────────────────
    SITE_NAME: str = "Race Photos"
    SITE_TAGLINE: str = "Your race, your photos."

    # ── Email ─────────────────────────────────────────────────────────────────
    EMAIL_ENABLED: bool = False
    EMAIL_PROVIDER: str = "brevo"
    BREVO_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = ""
    EMAIL_FROM_NAME: str = ""
    SUPPORT_EMAIL: str = ""
    ORDER_EMAIL_REQUIRED: bool = True
    BREVO_WEBHOOK_SECRET: str = ""


settings = Settings()
