from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .config import settings
from .recovery import ensure_job, exclusion
from .stripe_pricing import apply_checkout_session_pricing, stripe_expandable_id
from .delivery import ensure_delivery_for_order
from .models import (
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
    ensure_job(db, order.id, "email", comm.id)
    return comm.id


def mark_order_ready(
    order: Order,
    db: Session,
    *,
    payment_intent_id: str | None = None,
    customer_email: str | None = None,
    initiated_by: str = "system",
) -> int | None:
    db.query(Order).filter_by(id=order.id).with_for_update().one()
    if exclusion(order, db):
        return None
    order.status = OrderStatus.READY
    if payment_intent_id:
        order.stripe_payment_intent_id = payment_intent_id
    if customer_email:
        order.email = customer_email
    if order.paid_at is None:
        order.paid_at = datetime.now(timezone.utc)

    ensure_delivery_for_order(order, db)
    return create_download_ready_email(order, db, initiated_by=initiated_by)


def confirm_payment(order, session, db, *, actor="system"):
    """All callers supply a signed event or a server-retrieved Checkout Session."""
    db.query(Order).filter_by(id=order.id).with_for_update().populate_existing().one()
    if session.get("id") != order.stripe_session_id or exclusion(order, db):
        return False, None
    paid = session.get("payment_status") == "paid"
    free = (session.get("payment_status") == "no_payment_required"
            and session.get("status") == "complete" and session.get("amount_total") == 0)
    if not (paid or free):
        return False, None
    pricing = apply_checkout_session_pricing(order, session, db)
    if exclusion(order, db):
        return False, None
    if pricing:
        order.stripe_pricing_status = "QUEUED"
        ensure_job(db, order.id, "pricing", order.id)
    communication_id = mark_order_ready(order, db,
        payment_intent_id=stripe_expandable_id(session.get("payment_intent")),
        customer_email=session.get("customer_email") or (session.get("customer_details") or {}).get("email"), initiated_by=actor)
    return True, communication_id
