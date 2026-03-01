from datetime import datetime, timezone
import uuid as _uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.order_access import create_order_access_token
from app.schemas import CheckoutOut, CheckoutRequest
from photostore.config import settings
from photostore.models import Cart, Order, OrderItem, OrderStatus

router = APIRouter(prefix="/api", tags=["checkout"])

stripe.api_key = settings.STRIPE_SECRET_KEY


def _require_stripe() -> None:
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID:
        raise HTTPException(503, "Stripe is not configured on this server")


@router.post("/checkout", response_model=CheckoutOut)
def create_checkout(req: CheckoutRequest, db: Session = Depends(get_db)) -> CheckoutOut:
    _require_stripe()
    cart = db.query(Cart).filter(Cart.id == req.cart_id).first()
    if not cart:
        raise HTTPException(404, "Cart not found")

    # Reject expired carts
    if cart.expires_at and datetime.now(timezone.utc) > cart.expires_at:
        raise HTTPException(410, "Cart has expired")

    photo_ids: list[str] = cart.items_json
    count = len(photo_ids)

    if count == 0:
        raise HTTPException(400, "Cart is empty")

    # Look up actual unit price from Stripe so we can record it
    price_obj = stripe.Price.retrieve(settings.STRIPE_PRICE_ID)
    unit_amount_pence: int = price_obj.unit_amount or 0

    # Create the order row first so we can use the numeric ID in the Stripe
    # success URL. The stripe_session_id gets a unique placeholder until the
    # real session ID is available a few lines below.
    order = Order(
        stripe_session_id=f"pending_{_uuid.uuid4()}",
        email=cart.email or "",
        status=OrderStatus.PENDING,
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

    # Create Stripe Checkout session — success URL uses our numeric order ID
    # so the frontend can poll GET /api/orders/{order_id} immediately on return.
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": count}],
        customer_email=cart.email or None,
        metadata={"cart_id": str(cart.id), "event_id": str(cart.event_id)},
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
