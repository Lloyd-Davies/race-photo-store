import ipaddress
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str
    STORAGE_ROOT: str = "/data/photos"
    STORAGE_BACKEND: str = "local"
    ZIP_STORAGE_BACKEND: str = ""
    PROOF_STORAGE_BACKEND: str = "local"
    ORIGINAL_STORAGE_BACKEND: str = "local"
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    PUBLIC_BASE_URL: str = ""
    ADMIN_TOKEN: str = ""
    ADMIN_SESSION_SECRET: str = ""
    ADMIN_SESSION_TTL_MINUTES: int = 30
    ADMIN_REFRESH_TTL_HOURS: int = 12
    EVENT_ACCESS_TTL_HOURS: int = 12
    ORDER_ACCESS_TTL_HOURS: int = 720
    DOWNLOAD_MAX_DOWNLOADS: int = 100
    ZIP_TTL_DAYS: int = 3
    ZIP_CLEANUP_ENABLED: bool = True
    CACHE_ROOT: str = "/data/photos/cache"
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = "photostore"
    R2_ENDPOINT_URL: str = ""
    R2_REGION: str = "auto"
    R2_PUBLIC_BASE_URL: str = ""
    MAX_PHOTO_UPLOAD_BYTES: int = 100 * 1024 * 1024
    CELERY_CONCURRENCY: int = 2
    UVICORN_WORKERS: int = 2

    # ── Branding ──────────────────────────────────────────────────────────────
    SITE_NAME: str = "Race Photos"
    SITE_TAGLINE: str = ""

    # Public search/social metadata. This is deliberately separate from
    # PUBLIC_BASE_URL, which may point at localhost for transactional links in
    # development. SEO URLs must always remain public, absolute HTTPS URLs.
    SEO_SITE_URL: str = "https://photos.example.com"
    SEO_DEFAULT_TITLE: str = "Race Photos | Race and Event Photos"
    SEO_TITLE_TEMPLATE: str = "{page} | {site_name}"
    SEO_DEFAULT_DESCRIPTION: str = (
        "Browse and purchase professional photographs from running, athletics "
        "and sporting events photographed by Race Photos."
    )
    SEO_LOGO_URL: str = "https://photos.example.com/favicon.svg"

    @field_validator(
        "SEO_SITE_URL",
        "SEO_LOGO_URL",
    )
    @classmethod
    def validate_public_seo_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname:
            raise ValueError("SEO URLs must be absolute HTTPS URLs")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            raise ValueError("SEO URLs must not use local or internal hostnames")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise ValueError("SEO URLs must not use private or non-global IP addresses")
        return cleaned

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
