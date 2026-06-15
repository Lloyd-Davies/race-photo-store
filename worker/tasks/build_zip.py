import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.db import SessionLocal
from photostore.models import Delivery, DeliveryZipStatus, Order, OrderActivity, OrderItem, OrderStatus, Photo
from photostore.storage import LocalStorageBackend, get_storage_backend

ZIP_ERROR_MAX_LENGTH = 1000


def _record_zip_failure(db, order_id: int, exc: Exception) -> None:
    delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
    if not delivery:
        return
    delivery.zip_status = DeliveryZipStatus.FAILED
    delivery.zip_error = str(exc)[:ZIP_ERROR_MAX_LENGTH]
    db.add(OrderActivity(
        order_id=order_id,
        actor="worker",
        action="ZIP_BUILD_FAILED",
        message="ZIP build failed",
        metadata_json={"error": str(exc)[:ZIP_ERROR_MAX_LENGTH]},
    ))
    db.commit()


@celery_app.task(name="tasks.build_zip.build_zip", bind=True, max_retries=3)
def build_zip(self, order_id: int) -> None:  # type: ignore[override]
    db = SessionLocal()
    try:
        order: Order | None = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
        if not delivery:
            raise ValueError(f"Delivery for order {order_id} not found")

        delivery.zip_status = DeliveryZipStatus.BUILDING
        delivery.zip_error = None
        delivery.zip_deleted_at = None
        db.add(OrderActivity(
            order_id=order_id,
            actor="worker",
            action="ZIP_BUILD_STARTED",
            message="ZIP build started",
        ))
        db.commit()

        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order_id)
            .order_by(OrderItem.id.asc())
            .all()
        )
        photo_ids = [item.photo_id for item in items]
        if not photo_ids:
            raise ValueError(f"Order {order_id} has no items")

        photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
        photo_map = {p.id: p for p in photos}

        cache_dir = Path(settings.CACHE_ROOT) / "orders" / str(order_id)
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_zip = cache_dir / f"order-{order_id}.zip.tmp"
        cache_zip = cache_dir / f"order-{order_id}.zip"
        tmp_zip.unlink(missing_ok=True)
        cache_zip.unlink(missing_ok=True)

        source_storage = LocalStorageBackend()
        zip_storage = get_storage_backend()
        zip_key = f"zips/order-{order_id}.zip"

        try:
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_STORED) as zf:
                for photo_id in photo_ids:
                    photo = photo_map.get(photo_id)
                    if not photo:
                        raise ValueError(f"Photo record missing for id={photo_id}")

                    original = source_storage.local_path(photo.original_path)
                    if not original.exists():
                        raise FileNotFoundError(
                            f"Original not found: {original}. "
                            "If this event is archived, run restore_event first."
                        )

                    zf.write(original, arcname=f"{photo_id}.jpg")

            tmp_zip.replace(cache_zip)
            zip_storage.upload_file(cache_zip, zip_key, content_type="application/zip")
        finally:
            tmp_zip.unlink(missing_ok=True)
            cache_zip.unlink(missing_ok=True)

        now = datetime.now(timezone.utc)
        delivery.zip_path = zip_key
        delivery.zip_status = DeliveryZipStatus.READY
        delivery.zip_created_at = now
        delivery.zip_expires_at = now + timedelta(days=settings.ZIP_TTL_DAYS)
        delivery.zip_deleted_at = None
        delivery.zip_error = None
        if order.status != OrderStatus.EXPIRED:
            order.status = OrderStatus.READY
        db.add(OrderActivity(
            order_id=order_id,
            actor="worker",
            action="ZIP_BUILD_READY",
            message="ZIP build completed",
            metadata_json={"zip_path": zip_key},
        ))
        db.commit()

    except Exception as exc:
        try:
            _record_zip_failure(db, order_id, exc)
        except Exception:
            pass

        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()
