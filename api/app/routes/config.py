from fastapi import APIRouter

from photostore.config import settings

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def get_site_config() -> dict:
    """Public endpoint — returns branding/display settings for the frontend.

    Changing SITE_NAME or SITE_TAGLINE on the server only requires restarting
    the api container; no image rebuild is needed.
    """
    return {
        "site_name": settings.SITE_NAME,
        "site_tagline": settings.SITE_TAGLINE,
    }
