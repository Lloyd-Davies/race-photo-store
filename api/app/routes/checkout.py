from datetime import datetime, timezone
import uuid as _uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.fulfillment import mark_order_ready
from app.order_access import create_order_access_token
from app.schemas import CheckoutOut, CheckoutRequest
from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.models import Cart, Event, Order, OrderItem, OrderStatus
from photostore.pricing import effective_photo_price_pence, get_app_settings

router = APIRouter(prefix="/api", tags=["checkout"])

stripe.api_key = settings.STRIPE_SECRET_KEY


def _require_stripe() -> None:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe is not configured on this server")


@router.post("/checkout", response_model=CheckoutOut)
def create_checkout(req: CheckoutRequest, db: Session = Depends(get_db)) -> CheckoutOut:
    cart = db.query(Cart).filter(Cart.id == req.cart_id).first()
    if not cart:
        raise HTTPException(404, "Cart not found")

    event = db.query(Event).filter(Event.id == cart.event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    # Reject expired carts
    if cart.expires_at and datetime.now(timezone.utc) > cart.expires_at:
        raise HTTPException(410, "Cart has expired")

    photo_ids: list[str] = cart.items_json
    count = len(photo_ids)

    if count == 0:
        raise HTTPException(400, "Cart is empty")

    app_settings = get_app_settings(db)
    unit_amount_pence = effective_photo_price_pence(event, app_settings)
    currency = app_settings.currency.lower()
    if unit_amount_pence < 0:
        raise HTTPException(503, "Checkout pricing is not configured on this server")
    if unit_amount_pence > 0:
        _require_stripe()

    # Create the order row first so we can use the numeric ID in the Stripe
    # success URL. The stripe_session_id gets a unique placeholder until the
    # real session ID is available a few lines below.
    order = Order(
        stripe_session_id=f"pending_{_uuid.uuid4()}",
        email=req.email or cart.email or "",
        status=OrderStatus.PENDING,
        currency=app_settings.currency,
    )
    db.add(order)
    db.flush()  # assigns order.id without committing

    for photo_id in photo_ids:
        db.add(
            OrderItem(
                order_id=order.id,
                photo_id=photo_id,
                unit_price_pence=unit_amount_pence,
            )
        )

    order_access_token, _ = create_order_access_token(order.id)

    if unit_amount_pence == 0:
        order.stripe_session_id = f"free_{_uuid.uuid4()}"
        comm_id = mark_order_ready(order, db)
        db.commit()
        if comm_id:
            celery_app.send_task("tasks.send_email.send_email", args=[comm_id])
        return CheckoutOut(
            order_id=order.id,
            stripe_checkout_url=None,
            order_access_token=order_access_token,
        )

    # Create Stripe Checkout session — success URL uses our numeric order ID
    # so the frontend can poll GET /api/orders/{order_id} immediately on return.
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": unit_amount_pence,
                    "product_data": {"name": f"{event.name} photo download"},
                },
                "quantity": count,
            }
        ],
        customer_email=req.email or cart.email or None,
        metadata={"cart_id": str(cart.id), "event_id": str(cart.event_id), "order_id": str(order.id)},
        allow_promotion_codes=app_settings.allow_stripe_promotion_codes,
        success_url=f"{settings.PUBLIC_BASE_URL}/orders/{order.id}?access_token={order_access_token}",
        cancel_url=f"{settings.PUBLIC_BASE_URL}/",
    )

    order.stripe_session_id = session.id
    db.commit()
    db.refresh(order)

    return CheckoutOut(
        order_id=order.id,
        stripe_checkout_url=session.url,
        order_access_token=order_access_token,
    )
