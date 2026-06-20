import logging

import stripe

from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.db import SessionLocal
from photostore.models import Order
from photostore.stripe_pricing import apply_checkout_session_pricing


logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="tasks.sync_stripe_pricing.sync_stripe_pricing",
    max_retries=3,
)
def sync_stripe_pricing(self, order_id: int) -> dict:
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return {"status": "missing", "order_id": order_id}
        if order.stripe_session_id.startswith(("pending_", "free_")):
            return {"status": "skipped", "order_id": order_id}
        if not settings.STRIPE_SECRET_KEY:
            order.stripe_pricing_status = "FAILED"
            order.stripe_pricing_error = "Stripe is not configured on the worker."
            db.commit()
            return {"status": "unconfigured", "order_id": order_id}

        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(
            order.stripe_session_id,
            expand=["discounts.promotion_code", "payment_intent.latest_charge"],
        )
        if not apply_checkout_session_pricing(order, session, db):
            raise ValueError("Stripe session did not contain pricing totals")
        db.commit()
        return {"status": "synced", "order_id": order_id}
    except Exception as exc:
        db.rollback()
        try:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                order.stripe_pricing_status = "FAILED"
                order.stripe_pricing_error = "Stripe pricing synchronization failed."
                db.commit()
        except Exception:
            db.rollback()
        logger.error(
            "stripe_pricing_sync_failed order_id=%s error_type=%s",
            order_id,
            type(exc).__name__,
        )
        if self.request.retries >= self.max_retries:
            return {"status": "failed", "order_id": order_id}
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    finally:
        db.close()
