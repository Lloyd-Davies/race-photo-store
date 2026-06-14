from datetime import datetime, timezone

from sqlalchemy.orm import Session

from photostore.config import settings
from photostore.delivery import ensure_delivery_for_order
from photostore.models import (
    Communication,
    CommunicationKind,
    CommunicationStatus,
    Order,
    OrderStatus,
)


def create_download_ready_email(order: Order, db: Session, initiated_by: str = "system") -> int | None:
    if not settings.EMAIL_ENABLED or not order.email:
        return None

    dedupe_key = f"download_ready:{order.id}"
    existing = db.query(Communication).filter(Communication.dedupe_key == dedupe_key).first()
    if existing:
        return None

    comm = Communication(
        order_id=order.id,
        kind=CommunicationKind.DOWNLOAD_READY,
        status=CommunicationStatus.QUEUED,
        provider="brevo",
        recipient_email=order.email,
        subject="Your photos are ready to download",
        template_key="DOWNLOAD_READY",
        initiated_by=initiated_by,
        dedupe_key=dedupe_key,
    )
    db.add(comm)
    db.flush()
    return comm.id


def mark_order_ready(
    order: Order,
    db: Session,
    *,
    payment_intent_id: str | None = None,
    customer_email: str | None = None,
    initiated_by: str = "system",
) -> int | None:
    order.status = OrderStatus.READY
    if payment_intent_id:
        order.stripe_payment_intent_id = payment_intent_id
    if customer_email:
        order.email = customer_email
    if order.paid_at is None:
        order.paid_at = datetime.now(timezone.utc)

    ensure_delivery_for_order(order, db)
    return create_download_ready_email(order, db, initiated_by=initiated_by)
