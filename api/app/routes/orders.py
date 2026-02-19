import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas import OrderOut
from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.models import Delivery, Order, OrderStatus

router = APIRouter(prefix="/api", tags=["orders"])
logger = logging.getLogger(__name__)


def _try_fulfill_from_stripe(order: Order, db: Session) -> None:
    """If the Stripe session is already paid, fulfill the order inline.

    This is a safety-net for environments where Stripe webhooks cannot reach
    the server (local dev, firewall, etc.).  It is called opportunistically
    when a PENDING order is fetched; failures are silently swallowed so they
    never cause the GET request itself to error.
    """
    if not settings.STRIPE_SECRET_KEY:
        return
    # Placeholder session IDs (created before the Stripe session exists) are
    # not retrievable — skip them.
    if order.stripe_session_id.startswith("pending_"):
        return
    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        sess = stripe.checkout.Session.retrieve(order.stripe_session_id)
        if sess.payment_status != "paid":
            return
        order.status = OrderStatus.PAID
        order.stripe_payment_intent_id = sess.payment_intent
        order.email = sess.customer_email or order.email
        order.paid_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(order)
        celery_app.send_task("tasks.build_zip.build_zip", args=[order.id])
        logger.info("Order %s fulfilled via Stripe polling (webhook fallback)", order.id)
    except Exception:
        logger.exception("Stripe polling fallback failed for order %s", order.id)


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)) -> OrderOut:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    # Webhook fallback: if still PENDING, check Stripe directly.
    if order.status == OrderStatus.PENDING:
        _try_fulfill_from_stripe(order, db)

    download_url: str | None = None
    if order.status == OrderStatus.READY:
        delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
        if delivery:
            download_url = f"{settings.PUBLIC_BASE_URL}/d/{delivery.token}"

    return OrderOut(id=order.id, status=order.status, download_url=download_url)
