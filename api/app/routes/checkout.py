from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas import CheckoutOut, CheckoutRequest
from photostore.config import settings
from photostore.models import Cart, Order, OrderItem, OrderStatus

router = APIRouter(prefix="/api", tags=["checkout"])

stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/checkout", response_model=CheckoutOut)
def create_checkout(req: CheckoutRequest, db: Session = Depends(get_db)) -> CheckoutOut:
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

    # Create Stripe Checkout session
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price": settings.STRIPE_PRICE_ID,
                "quantity": count,
            }
        ],
        customer_email=cart.email or None,
        metadata={
            "cart_id": str(cart.id),
            "event_id": str(cart.event_id),
        },
        success_url=f"{settings.PUBLIC_BASE_URL}/order/{{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.PUBLIC_BASE_URL}/",
    )

    # Persist order in PENDING state; items hold the price at time of checkout
    order = Order(
        stripe_session_id=session.id,
        email=cart.email or "",
        status=OrderStatus.PENDING,
    )
    db.add(order)
    db.flush()  # get order.id without committing

    for photo_id in photo_ids:
        db.add(
            OrderItem(
                order_id=order.id,
                photo_id=photo_id,
                unit_price_pence=unit_amount_pence,
            )
        )

    db.commit()
    db.refresh(order)

    return CheckoutOut(order_id=order.id, stripe_checkout_url=session.url)
