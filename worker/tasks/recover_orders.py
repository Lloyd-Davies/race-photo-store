"""Bounded replay of durable work; Redis is a transport, never the source of truth."""
from datetime import timedelta
from sqlalchemy import or_
import stripe
from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.db import SessionLocal
from photostore.fulfillment import confirm_payment
from photostore.models import Communication, CommunicationStatus, Delivery, DeliveryZipStatus, Order, OrderStatus, RecoveryActivation, RecoveryJob
from photostore.recovery import ensure_job, exclusion, now, task_lock
from photostore.stripe_pricing import stripe_object_dict

TASKS = {"email": "tasks.send_email.send_email", "zip": "tasks.build_zip.build_zip",
         "pricing": "tasks.sync_stripe_pricing.sync_stripe_pricing"}


def completed(job, order, db):
    if job.kind == "payment":
        missing_email = (settings.EMAIL_ENABLED and order.email and not db.query(Communication.id)
                         .filter_by(order_id=order.id, dedupe_key=f"download_ready:{order.id}").first())
        return order.status == OrderStatus.READY and order.delivery is not None and not missing_email
    if job.kind == "email":
        comm = db.get(Communication, job.target_id)
        return comm is None or comm.status in {CommunicationStatus.SENT, CommunicationStatus.DELIVERED, CommunicationStatus.BOUNCED, CommunicationStatus.BLOCKED}
    if job.kind == "zip":
        return order.delivery and order.delivery.zip_status == DeliveryZipStatus.READY
    return order.stripe_pricing_status == "SYNCED"


@celery_app.task(name="tasks.recover_orders.recover_orders")
def recover_orders():
    db = SessionLocal()
    try:
        with task_lock(db, 7210, 0) as acquired:
            if not acquired:
                return 0
            activation = db.get(RecoveryActivation, 1)
            if not activation:
                return 0
            # Repair paid rows whose delivery never materialised as well as
            # missed webhooks. Old rows are included only by an admin selection.
            candidates = db.query(Order).filter(Order.created_at >= activation.activated_at,
                Order.created_at <= now() - timedelta(minutes=15),
                ~Order.stripe_session_id.startswith("pending_"),
                ~Order.stripe_session_id.startswith("free_"),
                ~Order.id.in_(db.query(RecoveryJob.order_id).filter(RecoveryJob.kind == "payment")),
                or_(Order.status.in_([OrderStatus.PENDING, OrderStatus.FAILED, OrderStatus.PAID]),
                    (Order.status == OrderStatus.READY) & ~Order.delivery.has())).order_by(Order.id).limit(25).with_for_update().all()
            for order in candidates:
                job = ensure_job(db, order.id, "payment", order.id)
                reason = exclusion(order, db)
                if reason:
                    job.status, job.error = "EXCLUDED", reason
            db.commit()
            ids = [row.id for row in db.query(RecoveryJob).filter(RecoveryJob.status == "PENDING",
                RecoveryJob.next_attempt_at <= now()).order_by(RecoveryJob.next_attempt_at, RecoveryJob.id).limit(25)]
            for job_id in ids:
                job = db.get(RecoveryJob, job_id)
                if job is None:
                    continue  # An explicitly deleted order cascades its outbox.
                order = db.query(Order).filter_by(id=job.order_id).with_for_update().one()
                reason = exclusion(order, db)
                if reason:
                    job.status, job.error = "EXCLUDED", reason
                elif completed(job, order, db):
                    job.status, job.error = "DONE", None
                elif now() >= job.created_at + timedelta(hours=24):
                    job.status, job.error = "REVIEW", "Automatic recovery window elapsed; inspect and retry."
                    if job.kind == "zip" and order.delivery:
                        order.delivery.zip_status = DeliveryZipStatus.FAILED
                        order.delivery.zip_error = "Preparation could not finish. Retry ZIP generation or contact support."
                else:
                    job.attempts += 1
                    job.last_attempt_at = now()
                    job.next_attempt_at = now() + timedelta(seconds=min(3600, 300 * 2 ** min(job.attempts - 1, 4)))
                    db.commit()  # Durable claim before contacting a provider/broker.
                    try:
                        with db.begin_nested():
                            if job.kind == "payment":
                                if not settings.STRIPE_SECRET_KEY:
                                    raise ValueError("Stripe unavailable")
                                stripe.api_key = settings.STRIPE_SECRET_KEY
                                session = stripe.checkout.Session.retrieve(order.stripe_session_id,
                                    expand=["payment_intent.latest_charge"])
                                confirmed, _ = confirm_payment(order, stripe_object_dict(session), db)
                                expired = stripe_object_dict(session).get("status") == "expired" and not confirmed
                                if expired and order.status == OrderStatus.PENDING:
                                    order.status = OrderStatus.FAILED
                                job.status = "DONE" if confirmed or expired else "PENDING"
                                job.error = None if confirmed or expired else "Awaiting confirmed payment"
                            else:
                                celery_app.send_task(TASKS[job.kind], args=[job.target_id])
                                job.error = None
                    except Exception as exc:
                        job = db.get(RecoveryJob, job_id)
                        job.error = type(exc).__name__
                db.commit()
            return len(ids)
    finally:
        db.close()
