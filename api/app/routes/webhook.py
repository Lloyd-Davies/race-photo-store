from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.deps import get_db
from app.fulfillment import mark_order_ready
from app.rate_limit import enforce_rate_limit
from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.models import Order, OrderStatus

router = APIRouter(prefix="/api", tags=["stripe"])

stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    enforce_rate_limit(request, scope="stripe-webhook", limit=60, window_seconds=60)

    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Stripe is not configured on this server")

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except stripe.SignatureVerificationError:
        raise HTTPException(400, "Invalid Stripe signature")
    except Exception:
        raise HTTPException(400, "Webhook payload invalid")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        _handle_checkout_completed(session, db)

    return {"received": True}


def _handle_checkout_completed(session: dict, db: Session) -> None:
    order = (
        db.query(Order)
        .filter(Order.stripe_session_id == session["id"])
        .first()
    )

    if not order:
        # Unknown session — ignore (could be from a different integration)
        return

    if order.status != OrderStatus.PENDING:
        # Already processed (webhook delivered more than once)
        return

    comm_id = mark_order_ready(
        order,
        db,
        payment_intent_id=session.get("payment_intent"),
        customer_email=session.get("customer_email"),
    )
    db.commit()

    if comm_id:
        celery_app.send_task("tasks.send_email.send_email", args=[comm_id])
