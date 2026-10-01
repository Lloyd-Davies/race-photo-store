"""Database outbox. Call ensure_job before committing the associated change."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from .models import Delivery, Order, OrderRefund, OrderStatus, RecoveryActivation, RecoveryJob


def now():
    return datetime.now(timezone.utc)


def exclusion(order, db):
    db.flush()  # Include refund activity captured in this same transaction.
    if order.status == OrderStatus.EXPIRED:
        return "Order access expired"
    if order.stripe_amount_refunded_pence or db.query(OrderRefund.id).filter_by(order_id=order.id).first():
        return "Refund activity requires review"
    if order.paid_at and not order.items:
        return "Purchased photo records unavailable; review the order"
    delivery = db.query(Delivery).filter_by(order_id=order.id).first()
    if not delivery and order.paid_at:
        from .config import settings
        if order.paid_at + timedelta(hours=settings.ORDER_ACCESS_TTL_HOURS) <= now():
            return "Paid order access period expired"
    if delivery and (delivery.expires_at <= now() or delivery.download_count >= delivery.max_downloads):
        return "Delivery access expired or exhausted"
    return None


def retry_allowed(db, kind, target_id):
    job = db.query(RecoveryJob).filter_by(kind=kind, target_id=target_id).first()
    if job is not None and kind == "pricing" and job.status == "DONE":
        return True  # Explicit later Stripe syncs must still refresh refund totals.
    return job is None or (job.status not in {"REVIEW", "EXCLUDED"} and
                           now() < job.created_at + timedelta(hours=24))


def ensure_job(db, order_id, kind, target_id, *, delay=0, restart=False, approved=False):
    # The owning order must be locked by callers when competing transactions
    # can create the same target. The unique constraint is the final safeguard.
    job = db.query(RecoveryJob).filter_by(kind=kind, target_id=target_id).first()
    if job is None and not approved:
        order = db.get(Order, order_id)
        activation = db.get(RecoveryActivation, 1)
        selected = db.query(RecoveryJob.id).filter_by(order_id=order_id, kind="payment").first()
        if not activation or (order.created_at < activation.activated_at and not selected):
            return None
    if job is None:
        job = RecoveryJob(order_id=order_id, kind=kind, target_id=target_id,
                          next_attempt_at=now() + timedelta(seconds=delay))
        db.add(job)
        db.flush()
    elif restart:
        job.status = "PENDING"
        job.attempts = 0
        job.created_at = now()
        job.next_attempt_at = now()
        job.error = None
    return job


@contextmanager
def task_lock(db, namespace, target_id):
    """Dedicated session advisory lock survives task commits; crash releases it."""
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    with engine.connect() as connection:
        acquired = connection.execute(text("SELECT pg_try_advisory_lock(:ns, :id)"),
                                      {"ns": namespace, "id": target_id}).scalar()
        try:
            yield bool(acquired)
        finally:
            if acquired:
                connection.execute(text("SELECT pg_advisory_unlock(:ns, :id)"),
                                   {"ns": namespace, "id": target_id})
