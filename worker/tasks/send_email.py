"""Celery task for sending transactional emails.

Design:
- The communication row is created BEFORE this task is dispatched.
- The task receives only the communication_id (small Redis payload).
- Rendering happens here so the stored body_html/body_text is exactly what was sent.
- Retries update the existing row rather than creating a new one.
- Exponential backoff: 60s, 120s, 240s for retries 0-2.
"""

from __future__ import annotations

from datetime import datetime, timezone

from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.db import SessionLocal
from photostore.email_provider import EmailMessage, ProviderError, get_provider
from photostore.email_templates import (
    render_delivery_reset,
    render_download_ready,
    render_order_confirmed,
)
from photostore.email_types import CommunicationKind, CommunicationStatus
from photostore.models import Communication, Delivery, Event, Order, OrderItem

_RENDER_MAP = {
    CommunicationKind.ORDER_CONFIRMED: render_order_confirmed,
    CommunicationKind.DOWNLOAD_READY: render_download_ready,
    CommunicationKind.DELIVERY_RESET: render_delivery_reset,
}


def _get_provider():
    """Thin wrapper so tests can monkeypatch this module attribute."""
    return get_provider()


def _build_context(order: Order, db) -> dict:
    """Build the template context dict from an order and its relationships."""
    delivery: Delivery | None = order.delivery

    # Resolve event name from order items -> photo -> event
    event_name = ""
    event_slug = ""
    item = db.query(OrderItem).filter(OrderItem.order_id == order.id).first()
    if item and item.photo and item.photo.event:
        event_name = item.photo.event.name
        event_slug = item.photo.event.slug
    elif delivery:
        event_slug = delivery.event_slug
        event_name = event_slug

    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    order_status_url = f"{base_url}/orders/{order.id}"

    direct_download_url = ""
    download_expires_at = ""
    max_downloads = ""
    if delivery:
        direct_download_url = f"{base_url}/download/{delivery.token}"
        download_expires_at = delivery.expires_at.strftime("%d %B %Y") if delivery.expires_at else ""
        max_downloads = str(delivery.max_downloads)

    return {
        "site_name": settings.SITE_NAME,
        "support_email": settings.SUPPORT_EMAIL,
        "order_id": order.id,
        "event_name": event_name,
        "customer_email": order.email,
        "order_status_url": order_status_url,
        "direct_download_url": direct_download_url,
        "download_expires_at": download_expires_at,
        "max_downloads": max_downloads,
    }


@celery_app.task(name="tasks.send_email.send_email", bind=True, max_retries=3)
def send_email(self, communication_id: int) -> None:  # type: ignore[override]
    db = SessionLocal()
    try:
        comm: Communication | None = (
            db.query(Communication).filter(Communication.id == communication_id).first()
        )
        if not comm:
            raise ValueError(f"Communication {communication_id} not found")

        order: Order | None = (
            db.query(Order).filter(Order.id == comm.order_id).first()
        )
        if not order:
            raise ValueError(f"Order for communication {communication_id} not found")

        # Render template
        render_fn = _RENDER_MAP.get(comm.kind)
        if not render_fn:
            raise ValueError(f"No template for kind {comm.kind}")

        ctx = _build_context(order, db)
        html_body, text_body = render_fn(ctx)

        # Store rendered bodies before attempting send
        comm.body_html = html_body
        comm.body_text = text_body
        db.commit()

        # Send via provider
        provider = _get_provider()
        msg = EmailMessage(
            to_email=comm.recipient_email,
            to_name=comm.recipient_email,
            subject=comm.subject,
            html_body=html_body,
            text_body=text_body,
            from_email=settings.EMAIL_FROM_ADDRESS,
            from_name=settings.EMAIL_FROM_NAME,
        )
        message_id = provider.send(msg)

        comm.status = CommunicationStatus.SENT
        comm.provider_message_id = message_id
        comm.sent_at = datetime.now(timezone.utc)
        db.commit()

    except ProviderError as exc:
        countdown = (2 ** self.request.retries) * 60
        try:
            comm_id = communication_id
            fail_comm = db.query(Communication).filter(Communication.id == comm_id).first()
            if fail_comm and self.request.retries >= self.max_retries:
                fail_comm.status = CommunicationStatus.FAILED
                fail_comm.error_message = str(exc)
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=countdown)

    except Exception as exc:
        # Non-retryable error or retries exhausted — mark FAILED
        try:
            fail_comm = db.query(Communication).filter(Communication.id == communication_id).first()
            if fail_comm:
                fail_comm.status = CommunicationStatus.FAILED
                fail_comm.error_message = str(exc)
                db.commit()
        except Exception:
            pass
        raise

    finally:
        db.close()
