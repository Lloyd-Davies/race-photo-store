import logging

from sqlalchemy.orm import Session

from app.order_activity import record_order_activity
from photostore.celery_app import celery_app
from photostore.email_types import CommunicationStatus
from photostore.models import Communication


logger = logging.getLogger(__name__)


def enqueue_communication_after_commit(
    db: Session,
    *,
    communication_id: int,
    order_id: int | None,
    actor: str,
) -> bool:
    try:
        celery_app.send_task("tasks.send_email.send_email", args=[communication_id])
        return True
    except Exception as exc:
        error_type = type(exc).__name__
        logger.error(
            "communication_enqueue_failed communication_id=%s order_id=%s actor=%s error_type=%s",
            communication_id,
            order_id,
            actor,
            error_type,
        )

        try:
            communication = (
                db.query(Communication)
                .filter(Communication.id == communication_id)
                .first()
            )
            if communication:
                communication.status = CommunicationStatus.FAILED
                communication.error_message = "Email task could not be queued; retry from admin."

            record_order_activity(
                db,
                order_id=order_id,
                action="EMAIL_QUEUE_FAILED",
                message="Email task could not be queued",
                actor=actor,
                metadata={
                    "communication_id": communication_id,
                    "error_type": error_type,
                },
            )
            db.commit()
        except Exception as record_exc:
            db.rollback()
            logger.error(
                "communication_enqueue_failure_recording_failed communication_id=%s "
                "order_id=%s actor=%s error_type=%s",
                communication_id,
                order_id,
                actor,
                type(record_exc).__name__,
            )
        return False
