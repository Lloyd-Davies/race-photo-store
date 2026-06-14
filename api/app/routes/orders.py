import logging
from datetime import datetime, timezone
from urllib.parse import quote

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.deps import get_db
from app.fulfillment import mark_order_ready
from app.order_access import verify_order_access_token
from app.rate_limit import enforce_rate_limit
from app.schemas import OrderDownloadItemOut, OrderOut, OrderZipOut
from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.delivery import ensure_delivery_for_order
from photostore.models import Delivery, DeliveryZipStatus, Order, OrderItem, OrderStatus
from photostore.storage import get_storage_backend

router = APIRouter(prefix="/api", tags=["orders"])
logger = logging.getLogger(__name__)


def _base_url() -> str:
    return settings.PUBLIC_BASE_URL.rstrip("/")


def _zip_expired(delivery: Delivery) -> bool:
    return bool(
        delivery.zip_expires_at
        and datetime.now(timezone.utc) > delivery.zip_expires_at
    )


def _zip_file_exists(delivery: Delivery) -> bool:
    if not delivery.zip_path:
        return False
    try:
        return get_storage_backend().exists(delivery.zip_path)
    except ValueError:
        return False


def _zip_out(delivery: Delivery | None) -> OrderZipOut:
    if not delivery:
        return OrderZipOut()

    status = delivery.zip_status or DeliveryZipStatus.NOT_REQUESTED
    is_ready = (
        status == DeliveryZipStatus.READY
        and not _zip_expired(delivery)
        and _zip_file_exists(delivery)
    )

    if status == DeliveryZipStatus.READY and not is_ready:
        status = DeliveryZipStatus.EXPIRED

    return OrderZipOut(
        status=status,
        download_url=(f"{_base_url()}/d/{delivery.token}" if is_ready else None),
        expires_at=(delivery.zip_expires_at if is_ready else None),
        error=delivery.zip_error if status == DeliveryZipStatus.FAILED else None,
    )


def _item_urls(delivery: Delivery, items: list[OrderItem]) -> list[OrderDownloadItemOut]:
    base_url = _base_url()
    return [
        OrderDownloadItemOut(
            photo_id=item.photo_id,
            proof_url=(
                f"{base_url}/d/{delivery.token}/photos/"
                f"{quote(item.photo_id, safe='')}/proof"
            ),
            view_url=(
                f"{base_url}/d/{delivery.token}/photos/"
                f"{quote(item.photo_id, safe='')}/view"
            ),
            download_url=(
                f"{base_url}/d/{delivery.token}/photos/"
                f"{quote(item.photo_id, safe='')}"
            ),
        )
        for item in items
    ]


def _order_out(order: Order, delivery: Delivery | None, db: Session) -> OrderOut:
    zip_state = _zip_out(delivery)
    photo_items: list[OrderDownloadItemOut] = []

    if order.status == OrderStatus.READY and delivery:
        items = (
            db.query(OrderItem)
            .filter(OrderItem.order_id == order.id)
            .order_by(OrderItem.id.asc())
            .all()
        )
        photo_items = _item_urls(delivery, items)

    return OrderOut(
        id=order.id,
        status=order.status,
        download_url=zip_state.download_url,
        zip=zip_state,
        items=photo_items,
        download_items=photo_items,
    )


def _require_order_access(
    order_id: int,
    access_token: str | None,
    x_order_access: str | None,
) -> None:
    provided_token = x_order_access or access_token
    if not verify_order_access_token(provided_token, order_id):
        raise HTTPException(404, "Order not found")


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
        comm_id = mark_order_ready(
            order,
            db,
            payment_intent_id=sess.payment_intent,
            customer_email=sess.customer_email or None,
        )
        db.commit()
        db.refresh(order)
        if comm_id:
            celery_app.send_task("tasks.send_email.send_email", args=[comm_id])
        logger.info("Order %s fulfilled via Stripe polling (webhook fallback)", order.id)
    except Exception:
        logger.exception("Stripe polling fallback failed for order %s", order.id)


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    request: Request,
    access_token: str | None = Query(default=None),
    x_order_access: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> OrderOut:
    enforce_rate_limit(request, scope="order-status", limit=120, window_seconds=60)

    _require_order_access(order_id, access_token, x_order_access)

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    # Webhook fallback: if still PENDING, check Stripe directly.
    if order.status == OrderStatus.PENDING:
        _try_fulfill_from_stripe(order, db)
        db.refresh(order)

    delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
    return _order_out(order, delivery, db)


@router.post("/orders/{order_id}/zip", response_model=OrderZipOut)
def prepare_order_zip(
    order_id: int,
    request: Request,
    access_token: str | None = Query(default=None),
    x_order_access: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> OrderZipOut:
    enforce_rate_limit(request, scope="order-zip", limit=60, window_seconds=60)
    _require_order_access(order_id, access_token, x_order_access)

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    if order.status == OrderStatus.PENDING:
        raise HTTPException(409, "Order is not ready yet")
    if order.status == OrderStatus.EXPIRED:
        raise HTTPException(410, "Order access has expired")
    if order.status == OrderStatus.FAILED:
        raise HTTPException(409, "Order is not available")
    if order.status == OrderStatus.PAID:
        order.status = OrderStatus.READY

    delivery = ensure_delivery_for_order(order, db)
    zip_state = _zip_out(delivery)
    if zip_state.status == DeliveryZipStatus.READY:
        db.commit()
        return zip_state
    if zip_state.status == DeliveryZipStatus.BUILDING:
        db.commit()
        return zip_state

    delivery.zip_status = DeliveryZipStatus.BUILDING
    delivery.zip_error = None
    delivery.zip_deleted_at = None
    delivery.zip_expires_at = None
    db.commit()

    celery_app.send_task("tasks.build_zip.build_zip", args=[order.id])
    db.refresh(delivery)
    return _zip_out(delivery)
