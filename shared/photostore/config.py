import ipaddress
from string import Formatter
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
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
    SITE_TAGLINE: str = "Your race, your photos."

    # Public search/social metadata. This is deliberately separate from
    # PUBLIC_BASE_URL, which may point at localhost for transactional links in
    # development. SEO URLs must always remain public, absolute HTTPS URLs.
    SEO_SITE_URL: str = ""
    SEO_DEFAULT_TITLE: str = ""
    SEO_TITLE_TEMPLATE: str = "{page} | {site_name}"
    SEO_DEFAULT_DESCRIPTION: str = (
        "Browse and purchase photographs from running, athletics and sporting events."
    )
    SEO_LOGO_URL: str = ""

    @field_validator("SEO_SITE_URL")
    @classmethod
    def validate_site_origin(cls, value: str) -> str:
        if not value.strip():
            return ""
        cleaned = cls.validate_public_seo_url(value)
        parsed = urlparse(cleaned)
        if parsed.path or parsed.query or parsed.fragment:
            raise ValueError("SEO_SITE_URL must be an HTTPS origin without a path, query or fragment")
        return cleaned

    @staticmethod
    def validate_public_seo_url(value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlparse(cleaned)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname:
            raise ValueError("SEO URLs must be absolute HTTPS URLs")
        if parsed.username or parsed.password:
            raise ValueError("SEO URLs must not contain credentials")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            raise ValueError("SEO URLs must not use local or internal hostnames")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise ValueError("SEO URLs must not use private or non-global IP addresses")
        return cleaned

    @field_validator("SEO_LOGO_URL")
    @classmethod
    def validate_optional_logo_url(cls, value: str) -> str:
        return cls.validate_public_seo_url(value) if value.strip() else ""

    @field_validator("SEO_TITLE_TEMPLATE")
    @classmethod
    def validate_title_template(cls, value: str) -> str:
        try:
            fields = list(Formatter().parse(value))
        except ValueError:
            raise ValueError("SEO_TITLE_TEMPLATE must have balanced braces") from None
        for _, field, spec, conversion in fields:
            if field is not None and (field not in {"page", "site_name"} or spec or conversion):
                raise ValueError("SEO_TITLE_TEMPLATE supports only {page} and {site_name}")
        return value

    @model_validator(mode="after")
    def derive_logo_url(self):
        if not self.SEO_SITE_URL:
            # Local transactional URLs must never become public search metadata.
            public_url = self.PUBLIC_BASE_URL.strip().rstrip("/")
            self.SEO_SITE_URL = (
                self.validate_site_origin(public_url)
                if public_url.startswith("https://") else "https://photos.example.com"
            )
        if not self.EMAIL_FROM_NAME.strip():
            self.EMAIL_FROM_NAME = self.SITE_NAME
        if not self.SEO_DEFAULT_TITLE.strip():
            self.SEO_DEFAULT_TITLE = f"{self.SITE_NAME} | Race and Event Photos"
        if not self.SEO_LOGO_URL:
            self.SEO_LOGO_URL = f"{self.SEO_SITE_URL}/favicon.svg"
        return self

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
