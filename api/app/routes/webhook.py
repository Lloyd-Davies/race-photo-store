from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.deps import get_db
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
    except Exception as exc:
        raise HTTPException(400, f"Webhook error: {exc}")

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

    order.status = OrderStatus.PAID
    order.stripe_payment_intent_id = session.get("payment_intent")
    order.email = session.get("customer_email") or order.email
    order.paid_at = datetime.now(timezone.utc)
    db.commit()

    # Dispatch the zip-building task to the worker
    celery_app.send_task("tasks.build_zip.build_zip", args=[order.id])
