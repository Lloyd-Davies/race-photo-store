import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from photostore.models import Order, StripeEvent


def _plain_json(value: Any) -> dict[str, Any]:
    return json.loads(json.dumps(value, default=str))


def _get_attr_or_item(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _nested_object(event: Any) -> Any:
    data = _get_attr_or_item(event, "data", {}) or {}
    if isinstance(data, dict):
        return data.get("object") or {}
    return getattr(data, "object", {}) or {}


def _event_created_at(event: Any) -> datetime | None:
    created = _get_attr_or_item(event, "created")
    if not created:
        return None
    try:
        return datetime.fromtimestamp(int(created), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _find_order(db: Session, stripe_object: Any) -> Order | None:
    session_id = _get_attr_or_item(stripe_object, "id")
    payment_intent_id = _get_attr_or_item(stripe_object, "payment_intent")
    if not payment_intent_id:
        payment_intent_id = _get_attr_or_item(stripe_object, "payment_intent_id")

    metadata = _get_attr_or_item(stripe_object, "metadata", {}) or {}
    order_id = None
    if isinstance(metadata, dict):
        raw_order_id = metadata.get("order_id")
        try:
            order_id = int(raw_order_id) if raw_order_id else None
        except (TypeError, ValueError):
            order_id = None

    query = db.query(Order)
    if order_id is not None:
        order = query.filter(Order.id == order_id).first()
        if order:
            return order
    if session_id:
        order = query.filter(Order.stripe_session_id == session_id).first()
        if order:
            return order
    if payment_intent_id:
        return query.filter(Order.stripe_payment_intent_id == payment_intent_id).first()
    return None


def store_stripe_event(db: Session, event: Any, *, status: str = "RECEIVED", error: str | None = None) -> StripeEvent:
    stripe_event_id = str(_get_attr_or_item(event, "id", "") or "")
    if not stripe_event_id:
        stripe_event_id = f"manual_{datetime.now(timezone.utc).timestamp()}"

    existing = db.query(StripeEvent).filter(StripeEvent.stripe_event_id == stripe_event_id).first()
    if existing:
        return existing

    stripe_object = _nested_object(event)
    order = _find_order(db, stripe_object)
    payment_intent_id = _get_attr_or_item(stripe_object, "payment_intent")
    if not payment_intent_id:
        payment_intent_id = _get_attr_or_item(stripe_object, "payment_intent_id")

    stored = StripeEvent(
        stripe_event_id=stripe_event_id,
        event_type=str(_get_attr_or_item(event, "type", "unknown")),
        order_id=order.id if order else None,
        stripe_session_id=_get_attr_or_item(stripe_object, "id"),
        payment_intent_id=payment_intent_id,
        livemode=bool(_get_attr_or_item(event, "livemode", False)),
        payload_json=_plain_json(event),
        processing_status=status,
        error_message=error,
        stripe_created_at=_event_created_at(event),
    )
    db.add(stored)
    return stored
