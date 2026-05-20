from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from photostore.config import settings
from photostore.pricing import get_app_settings

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def get_site_config(db: Session = Depends(get_db)) -> dict:
    """Public endpoint — returns branding/display settings for the frontend.

    Changing SITE_NAME or SITE_TAGLINE on the server only requires restarting
    the api container; no image rebuild is needed.
    """
    app_settings = get_app_settings(db)
    return {
        "site_name": settings.SITE_NAME,
        "site_tagline": settings.SITE_TAGLINE,
        "allow_stripe_promotion_codes": app_settings.allow_stripe_promotion_codes,
    }
