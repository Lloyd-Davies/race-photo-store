from sqlalchemy.orm import Session

from .models import AppSettings, Event

APP_SETTINGS_ID = 1
DEFAULT_PHOTO_PRICE_PENCE = 500
DEFAULT_CURRENCY = "GBP"


def normalize_currency(currency: str) -> str:
    return currency.strip().upper()


def get_app_settings(db: Session) -> AppSettings:
    app_settings = db.query(AppSettings).filter(AppSettings.id == APP_SETTINGS_ID).first()
    if app_settings:
        return app_settings

    app_settings = AppSettings(
        id=APP_SETTINGS_ID,
        default_photo_price_pence=DEFAULT_PHOTO_PRICE_PENCE,
        currency=DEFAULT_CURRENCY,
        allow_stripe_promotion_codes=False,
    )
    db.add(app_settings)
    db.flush()
    return app_settings


def effective_photo_price_pence(event: Event, app_settings: AppSettings) -> int:
    return event.photo_price_pence or app_settings.default_photo_price_pence
