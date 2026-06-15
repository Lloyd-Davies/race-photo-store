from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.deps import get_db
from app.fulfillment import mark_order_ready
from app.order_activity import record_order_activity
from app.rate_limit import enforce_rate_limit
from app.stripe_event_store import store_stripe_event
from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.models import Order, OrderStatus, StripeEvent

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

    event_id = event.get("id") if isinstance(event, dict) else getattr(event, "id", None)
    if event_id and db.query(StripeEvent).filter(StripeEvent.stripe_event_id == event_id).first():
        return {"received": True}

    stored = store_stripe_event(db, event)
    event_type = event["type"]

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(event["data"]["object"], db)
        stored.processing_status = "PROCESSED"
    elif event_type == "checkout.session.expired":
        _handle_checkout_expired(event["data"]["object"], db)
        stored.processing_status = "PROCESSED"
    elif event_type in {"payment_intent.payment_failed", "charge.failed"}:
        _handle_payment_failed(event["data"]["object"], db, event_type)
        stored.processing_status = "PROCESSED"
    elif event_type in {"charge.refunded", "refund.created", "refund.updated"}:
        _record_refund_event(event["data"]["object"], db, event_type)
        stored.processing_status = "PROCESSED"
    else:
        stored.processing_status = "IGNORED"

    db.commit()
    return {"received": True}


def _handle_checkout_completed(session: dict, db: Session) -> None:
    order = db.query(Order).filter(Order.stripe_session_id == session["id"]).first()
    if not order or order.status != OrderStatus.PENDING:
        return

    comm_id = mark_order_ready(
        order,
        db,
        payment_intent_id=session.get("payment_intent"),
        customer_email=session.get("customer_email"),
    )
    record_order_activity(
        db,
        order_id=order.id,
        action="STRIPE_CHECKOUT_COMPLETED",
        message="Stripe Checkout session completed",
        actor="stripe",
        metadata={
            "stripe_session_id": session.get("id"),
            "payment_intent_id": session.get("payment_intent"),
        },
    )

    if comm_id:
        celery_app.send_task("tasks.send_email.send_email", args=[comm_id])


def _handle_checkout_expired(session: dict, db: Session) -> None:
    order = db.query(Order).filter(Order.stripe_session_id == session["id"]).first()
    if not order or order.status != OrderStatus.PENDING:
        return

    order.status = OrderStatus.FAILED
    record_order_activity(
        db,
        order_id=order.id,
        action="STRIPE_CHECKOUT_EXPIRED",
        message="Stripe Checkout session expired before payment",
        actor="stripe",
        metadata={"stripe_session_id": session.get("id")},
    )


def _handle_payment_failed(stripe_object: dict, db: Session, event_type: str) -> None:
    payment_intent_id = stripe_object.get("id") or stripe_object.get("payment_intent")
    if not payment_intent_id:
        return

    order = db.query(Order).filter(Order.stripe_payment_intent_id == payment_intent_id).first()
    if not order:
        return

    if order.status == OrderStatus.PENDING:
        order.status = OrderStatus.FAILED
    record_order_activity(
        db,
        order_id=order.id,
        action="STRIPE_PAYMENT_FAILED",
        message="Stripe reported a failed payment",
        actor="stripe",
        metadata={"event_type": event_type, "payment_intent_id": payment_intent_id},
    )


def _record_refund_event(stripe_object: dict, db: Session, event_type: str) -> None:
    payment_intent_id = stripe_object.get("payment_intent")
    if not payment_intent_id:
        charge = stripe_object.get("charge")
        payment_intent_id = charge.get("payment_intent") if isinstance(charge, dict) else None
    if not payment_intent_id:
        return

    order = db.query(Order).filter(Order.stripe_payment_intent_id == payment_intent_id).first()
    if not order:
        return

    record_order_activity(
        db,
        order_id=order.id,
        action="STRIPE_REFUND_EVENT",
        message="Stripe reported refund activity",
        actor="stripe",
        metadata={"event_type": event_type, "payment_intent_id": payment_intent_id},
    )
