# Expose the Celery app object so `celery -A tasks worker` can find it,
# and import task modules so Celery registers all tasks on startup.
from photostore.celery_app import celery_app as app  # noqa: F401

from .archive import archive_event, restore_event  # noqa: F401
from .build_zip import build_zip  # noqa: F401
from .cleanup_expired_zips import cleanup_expired_zips  # noqa: F401
from .send_email import send_email  # noqa: F401
from .sync_stripe_pricing import sync_stripe_pricing  # noqa: F401
