import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .config import settings
from .models import Delivery, DeliveryZipStatus, Event, Order, OrderItem, Photo


def order_access_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=settings.ORDER_ACCESS_TTL_HOURS)


def event_slug_for_order(order_id: int, db: Session) -> str:
    row = (
        db.query(Event.slug)
        .join(Photo, Photo.event_id == Event.id)
        .join(OrderItem, OrderItem.photo_id == Photo.id)
        .filter(OrderItem.order_id == order_id)
        .order_by(OrderItem.id.asc())
        .first()
    )
    return row[0] if row else "event"


def ensure_delivery_for_order(order: Order, db: Session) -> Delivery:
    delivery = db.query(Delivery).filter(Delivery.order_id == order.id).first()
    if delivery:
        if not delivery.event_slug:
            delivery.event_slug = event_slug_for_order(order.id, db)
        if not delivery.zip_status:
            delivery.zip_status = (
                DeliveryZipStatus.READY
                if delivery.zip_path
                else DeliveryZipStatus.NOT_REQUESTED
            )
        return delivery

    delivery = Delivery(
        order_id=order.id,
        token=str(uuid.uuid4()),
        zip_path=None,
        event_slug=event_slug_for_order(order.id, db),
        expires_at=order_access_expires_at(),
        max_downloads=settings.DOWNLOAD_MAX_DOWNLOADS,
        download_count=0,
        zip_status=DeliveryZipStatus.NOT_REQUESTED,
    )
    db.add(delivery)
    return delivery
