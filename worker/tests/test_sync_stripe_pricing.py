from datetime import datetime, timezone
import importlib
from unittest.mock import patch

from photostore.models import Order, OrderDiscount, OrderRefund, OrderStatus


def test_sync_stripe_pricing_persists_discount_and_refund_idempotently(
    db_session, monkeypatch
):
    from photostore.config import settings
    module = importlib.import_module("worker.tasks.sync_stripe_pricing")
    task = module.sync_stripe_pricing

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    order = Order(
        stripe_session_id="cs_worker_pricing",
        stripe_payment_intent_id="pi_worker_pricing",
        email="runner@example.com",
        status=OrderStatus.READY,
        paid_at=datetime.now(timezone.utc),
    )
    db_session.add(order)
    db_session.flush()
    session = {
        "id": order.stripe_session_id,
        "payment_status": "paid",
        "currency": "gbp",
        "amount_subtotal": 2000,
        "amount_total": 1400,
        "total_details": {
            "amount_discount": 600,
            "amount_tax": 0,
            "amount_shipping": 0,
            "breakdown": {"discounts": [
                {
                    "amount": 500,
                    "discount": {"id": "di_worker", "promotion_code": {
                        "id": "promo_worker", "code": "WORKER25",
                    }},
                },
                {
                    "amount": 100,
                    "discount": {"id": "di_bonus", "promotion_code": {
                        "id": "promo_bonus", "code": "BONUS",
                    }},
                },
            ]},
        },
        "discounts": [
            {
                "id": "di_worker",
                "promotion_code": {"id": "promo_worker", "code": "WORKER25"},
            },
            {
                "id": "di_bonus",
                "promotion_code": {"id": "promo_bonus", "code": "BONUS"},
            },
        ],
        "payment_intent": {
            "id": "pi_worker_pricing",
            "latest_charge": {
                "amount_refunded": 300,
                "refunds": {"data": [{
                    "id": "re_worker",
                    "amount": 300,
                    "currency": "gbp",
                    "status": "succeeded",
                    "created": int(datetime.now(timezone.utc).timestamp()),
                }]},
            },
        },
    }

    with (
        patch.object(module, "SessionLocal", return_value=db_session),
        patch.object(module.stripe.checkout.Session, "retrieve", return_value=session),
    ):
        first = task.run(order.id)
        second = task.run(order.id)

    assert first["status"] == "synced"
    assert second["status"] == "synced"
    assert order.stripe_amount_paid_pence == 1400
    assert order.stripe_amount_refunded_pence == 300
    assert db_session.query(OrderDiscount).filter(OrderDiscount.order_id == order.id).count() == 2
    assert db_session.query(OrderRefund).filter(OrderRefund.order_id == order.id).count() == 1
