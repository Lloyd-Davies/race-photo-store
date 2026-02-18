import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.db import SessionLocal
from photostore.models import Delivery, Order, OrderItem, OrderStatus, Photo

DOWNLOAD_TTL_DAYS = 30
MAX_DOWNLOADS = 5


@celery_app.task(name="tasks.build_zip.build_zip", bind=True, max_retries=3)
def build_zip(self, order_id: int) -> None:  # type: ignore[override]
    db = SessionLocal()
    try:
        order: Order | None = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Mark as building so the API can reflect progress
        order.status = OrderStatus.BUILDING
        db.commit()

        # Collect photo IDs from order items
        items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
        photo_ids = [item.photo_id for item in items]

        photos = db.query(Photo).filter(Photo.id.in_(photo_ids)).all()
        photo_map = {p.id: p for p in photos}

        storage_root = Path(settings.STORAGE_ROOT)
        zip_dir = storage_root / "zips"
        zip_dir.mkdir(parents=True, exist_ok=True)

        final_zip = zip_dir / f"order-{order_id}.zip"

        # Write to a temp file first; atomic rename prevents partial ZIPs being served
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", dir=zip_dir)
        os.close(tmp_fd)

        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_STORED) as zf:
                for photo_id in photo_ids:
                    photo = photo_map.get(photo_id)
                    if not photo:
                        raise ValueError(f"Photo record missing for id={photo_id}")

                    original = storage_root / photo.original_path
                    if not original.exists():
                        raise FileNotFoundError(
                            f"Original not found: {original}. "
                            "If this event is archived, run restore_event first."
                        )

                    zf.write(original, arcname=f"{photo_id}.jpg")

            shutil.move(tmp_path, final_zip)

        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        # Determine event slug for the download filename
        event_slug = photos[0].event.slug if photos else "event"

        # Create a tokenised delivery record
        delivery = Delivery(
            order_id=order_id,
            token=str(uuid.uuid4()),
            zip_path=f"zips/order-{order_id}.zip",
            event_slug=event_slug,
            expires_at=datetime.now(timezone.utc) + timedelta(days=DOWNLOAD_TTL_DAYS),
            max_downloads=MAX_DOWNLOADS,
            download_count=0,
        )
        db.add(delivery)

        order.status = OrderStatus.READY
        db.commit()

    except Exception as exc:
        # Mark order FAILED before retrying so the status is visible
        try:
            failed_order = db.query(Order).filter(Order.id == order_id).first()
            if failed_order:
                failed_order.status = OrderStatus.FAILED
                db.commit()
        except Exception:
            pass

        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()
