import logging

from sqlalchemy.orm import Session

from app.order_activity import record_order_activity
from photostore.celery_app import celery_app
from photostore.models import Order


logger = logging.getLogger(__name__)


def enqueue_order_pricing_sync_after_commit(
    db: Session,
    *,
    order_id: int,
    actor: str,
) -> bool:
    try:
        celery_app.send_task("tasks.sync_stripe_pricing.sync_stripe_pricing", args=[order_id])
        return True
    except Exception as exc:
        logger.error(
            "stripe_pricing_enqueue_failed order_id=%s actor=%s error_type=%s",
            order_id,
            actor,
            type(exc).__name__,
        )
        try:
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                order.stripe_pricing_status = "FAILED"
                order.stripe_pricing_error = "Stripe pricing task could not be queued."
            record_order_activity(
                db,
                order_id=order_id,
                action="STRIPE_PRICING_QUEUE_FAILED",
                message="Stripe pricing synchronization could not be queued",
                actor=actor,
                metadata={"error_type": type(exc).__name__},
            )
            db.commit()
        except Exception as record_exc:
            db.rollback()
            logger.error(
                "stripe_pricing_enqueue_recording_failed order_id=%s error_type=%s",
                order_id,
                type(record_exc).__name__,
            )
        return False
