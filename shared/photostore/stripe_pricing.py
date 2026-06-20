from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import Order, OrderDiscount, OrderRefund


SUCCESSFUL_REFUND_STATUSES = {"succeeded"}


def stripe_object_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"Unsupported Stripe object type: {type(value).__name__}")


def _nested_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None or isinstance(value, str):
        return {}
    return stripe_object_dict(value)


def _expandable_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return _nested_dict(value).get("id") or None


def stripe_expandable_id(value: Any) -> str | None:
    return _expandable_id(value)


def _stripe_timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OSError):
        return None


def _amount(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def apply_checkout_session_pricing(order: Order, session_value: Any, db: Session) -> bool:
    session = stripe_object_dict(session_value)
    amount_total = _amount(session.get("amount_total"))
    amount_subtotal = _amount(session.get("amount_subtotal"))
    if amount_total is None and amount_subtotal is None:
        return False

    details = _nested_dict(session.get("total_details"))
    order.stripe_amount_subtotal_pence = int(amount_subtotal or 0)
    order.stripe_discount_pence = _amount(details.get("amount_discount")) or 0
    order.stripe_tax_pence = _amount(details.get("amount_tax")) or 0
    order.stripe_shipping_pence = _amount(details.get("amount_shipping")) or 0
    order.stripe_amount_paid_pence = int(amount_total or 0)
    if session.get("currency"):
        order.currency = str(session["currency"]).upper()
    order.stripe_pricing_status = "SYNCED"
    order.stripe_pricing_error = None
    order.stripe_pricing_synced_at = datetime.now(timezone.utc)

    _replace_discounts(order, session, db)
    _apply_payment_intent_refunds(order, session.get("payment_intent"), db)
    return True


def _replace_discounts(order: Order, session: dict[str, Any], db: Session) -> None:
    discounts_value = session.get("discounts")
    if discounts_value is None:
        return

    discounts = [_nested_dict(value) for value in discounts_value]
    breakdown = _nested_dict(_nested_dict(session.get("total_details")).get("breakdown"))
    breakdown_rows = [_nested_dict(value) for value in breakdown.get("discounts") or []]
    amount_by_discount_id: dict[str, int] = {}
    breakdown_discount_by_id: dict[str, dict[str, Any]] = {}
    for row in breakdown_rows:
        discount = _nested_dict(row.get("discount"))
        discount_id = discount.get("id")
        if discount_id:
            amount_by_discount_id[str(discount_id)] = int(row.get("amount") or 0)
            breakdown_discount_by_id[str(discount_id)] = discount

    db.query(OrderDiscount).filter(OrderDiscount.order_id == order.id).delete(
        synchronize_session=False
    )
    aggregate_discount = int(order.stripe_discount_pence or 0)
    for index, base_discount in enumerate(discounts):
        discount_id = base_discount.get("id")
        discount = {**breakdown_discount_by_id.get(str(discount_id), {}), **base_discount}
        promotion = discount.get("promotion_code")
        promotion_dict = _nested_dict(promotion)
        source = _nested_dict(discount.get("source"))
        coupon = source.get("coupon") or discount.get("coupon")
        amount = amount_by_discount_id.get(str(discount_id)) if discount_id else None
        if amount is None and len(discounts) == 1:
            amount = aggregate_discount
        db.add(OrderDiscount(
            order_id=order.id,
            stripe_discount_id=str(discount_id) if discount_id else f"order-{order.id}-{index}",
            stripe_promotion_code_id=_expandable_id(promotion),
            promotion_code=promotion_dict.get("code") or None,
            stripe_coupon_id=_expandable_id(coupon),
            amount_pence=amount,
            currency=(order.currency or "GBP").upper(),
        ))


def apply_refund(order: Order, refund_value: Any, db: Session) -> OrderRefund | None:
    refund = stripe_object_dict(refund_value)
    refund_id = refund.get("id")
    if not refund_id or refund.get("amount") is None:
        return None
    stored = db.query(OrderRefund).filter(OrderRefund.stripe_refund_id == refund_id).first()
    if not stored:
        stored = OrderRefund(order_id=order.id, stripe_refund_id=str(refund_id))
        db.add(stored)
    stored.order_id = order.id
    stored.amount_pence = int(refund.get("amount") or 0)
    stored.currency = str(refund.get("currency") or order.currency or "GBP").upper()
    stored.status = str(refund.get("status") or "unknown")
    stored.reason = refund.get("reason")
    stored.stripe_created_at = _stripe_timestamp(refund.get("created"))
    db.flush()
    recalculate_order_refunds(order, db)
    return stored


def apply_charge_refunds(order: Order, charge_value: Any, db: Session) -> None:
    charge = _nested_dict(charge_value)
    refunds = _nested_dict(charge.get("refunds"))
    for refund in refunds.get("data") or []:
        apply_refund(order, refund, db)
    if charge.get("amount_refunded") is not None:
        order.stripe_amount_refunded_pence = int(charge.get("amount_refunded") or 0)


def _apply_payment_intent_refunds(order: Order, payment_intent_value: Any, db: Session) -> None:
    payment_intent = _nested_dict(payment_intent_value)
    latest_charge = payment_intent.get("latest_charge")
    if latest_charge and not isinstance(latest_charge, str):
        apply_charge_refunds(order, latest_charge, db)


def recalculate_order_refunds(order: Order, db: Session) -> None:
    successful_total = sum(
        refund.amount_pence
        for refund in db.query(OrderRefund).filter(OrderRefund.order_id == order.id).all()
        if refund.status in SUCCESSFUL_REFUND_STATUSES
    )
    order.stripe_amount_refunded_pence = successful_total
