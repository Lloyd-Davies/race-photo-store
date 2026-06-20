import logging
from typing import Any, Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.communication_queue import enqueue_communication_after_commit
from app.deps import get_db
from app.fulfillment import mark_order_ready
from app.order_activity import record_order_activity
from app.rate_limit import enforce_rate_limit
from app.stripe_event_store import store_stripe_event
from photostore.config import settings
from photostore.models import Order, OrderStatus, StripeEvent

router = APIRouter(prefix="/api", tags=["stripe"])

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

TERMINAL_EVENT_STATUSES = {"PROCESSED", "IGNORED"}


def _stripe_object_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"Unsupported Stripe object type: {type(value).__name__}")


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
        logger.warning(
            "stripe_webhook_signature_invalid payload_bytes=%s signature_present=%s",
            len(payload),
            bool(stripe_signature),
        )
        raise HTTPException(400, "Invalid Stripe signature")
    except Exception as exc:
        logger.warning(
            "stripe_webhook_payload_invalid payload_bytes=%s error_type=%s",
            len(payload),
            type(exc).__name__,
        )
        raise HTTPException(400, "Webhook payload invalid")

    event_id = event.get("id") if isinstance(event, dict) else getattr(event, "id", None)
    event_type = event["type"]
    existing = None
    if event_id:
        existing = db.query(StripeEvent).filter(StripeEvent.stripe_event_id == event_id).first()
    if existing and existing.processing_status in TERMINAL_EVENT_STATUSES:
        return {"received": True}

    stored = existing or store_stripe_event(db, event)
    communication_id = None
    order_id = stored.order_id

    try:
        if event_type == "checkout.session.completed":
            stripe_object = _stripe_object_dict(event["data"]["object"])
            communication_id, order_id = _handle_checkout_completed(stripe_object, db)
            stored.processing_status = "PROCESSED"
        elif event_type == "checkout.session.expired":
            _handle_checkout_expired(_stripe_object_dict(event["data"]["object"]), db)
            stored.processing_status = "PROCESSED"
        elif event_type in {"payment_intent.payment_failed", "charge.failed"}:
            _handle_payment_failed(
                _stripe_object_dict(event["data"]["object"]),
                db,
                event_type,
            )
            stored.processing_status = "PROCESSED"
        elif event_type in {"charge.refunded", "refund.created", "refund.updated"}:
            _record_refund_event(
                _stripe_object_dict(event["data"]["object"]),
                db,
                event_type,
            )
            stored.processing_status = "PROCESSED"
        else:
            stored.processing_status = "IGNORED"
        stored.error_message = None
        db.commit()
    except Exception as exc:
        error_type = type(exc).__name__
        db.rollback()
        try:
            failed = store_stripe_event(db, event, status="FAILED", error=error_type)
            failed.processing_status = "FAILED"
            failed.error_message = error_type
            db.commit()
        except Exception:
            db.rollback()
        logger.error(
            "stripe_webhook_processing_failed event_id=%s event_type=%s error_type=%s",
            event_id or "missing",
            event_type,
            error_type,
        )
        raise HTTPException(500, "Webhook processing failed")

    if communication_id:
        enqueue_communication_after_commit(
            db,
            communication_id=communication_id,
            order_id=order_id,
            actor="stripe",
        )

    logger.info(
        "stripe_webhook_processed event_id=%s event_type=%s status=%s",
        event_id or "missing",
        event_type,
        stored.processing_status,
    )
    return {"received": True}


def _handle_checkout_completed(session: dict, db: Session) -> tuple[int | None, int | None]:
    order = db.query(Order).filter(Order.stripe_session_id == session["id"]).first()
    if not order or order.status != OrderStatus.PENDING:
        return None, order.id if order else None

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

    return comm_id, order.id


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
