from datetime import datetime, timezone

from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.db import SessionLocal
from photostore.models import Delivery, DeliveryZipStatus
from photostore.storage import get_storage_backend


@celery_app.task(name="tasks.cleanup_expired_zips.cleanup_expired_zips")
def cleanup_expired_zips() -> int:
    if not settings.ZIP_CLEANUP_ENABLED:
        return 0

    db = SessionLocal()
    deleted = 0
    try:
        now = datetime.now(timezone.utc)
        deliveries = (
            db.query(Delivery)
            .filter(Delivery.zip_status == DeliveryZipStatus.READY)
            .filter(Delivery.zip_expires_at.isnot(None))
            .filter(Delivery.zip_expires_at < now)
            .all()
        )

        storage = get_storage_backend()
        for delivery in deliveries:
            if delivery.zip_path:
                try:
                    storage.delete(delivery.zip_path)
                    deleted += 1
                except FileNotFoundError:
                    pass

            delivery.zip_status = DeliveryZipStatus.EXPIRED
            delivery.zip_deleted_at = now

        db.commit()
        return deleted
    finally:
        db.close()
