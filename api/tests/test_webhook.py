import json
from unittest.mock import patch

import stripe


def _make_order(db_session, test_photos):
    """Helper: create a PENDING order with items directly."""
    from photostore.models import Order, OrderItem, OrderStatus

    order = Order(
        stripe_session_id="cs_test_webhook123",
        email="runner@example.com",
        status=OrderStatus.PENDING,
    )
    db_session.add(order)
    db_session.flush()

    for photo in test_photos:
        db_session.add(OrderItem(
            order_id=order.id,
            photo_id=photo.id,
            unit_price_pence=500,
        ))
    db_session.flush()
    return order


def test_webhook_stripe_not_configured(client):
    resp = client.post("/api/stripe/webhook", content=b"{}")
    assert resp.status_code == 503


def test_webhook_fulfills_order(client, db_session, test_photos, mock_celery_send_task, monkeypatch):
    from photostore.config import settings
    from photostore.models import OrderStatus

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake")

    order = _make_order(db_session, test_photos)

    event_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": order.stripe_session_id,
            "payment_intent": "pi_testfake",
            "customer_email": "runner@example.com",
        }},
    }

    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        resp = client.post(
            "/api/stripe/webhook",
            content=json.dumps(event_payload).encode(),
            headers={"stripe-signature": "t=1,v1=fakesig"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"received": True}

    db_session.refresh(order)
    assert order.status == OrderStatus.PAID
    assert order.stripe_payment_intent_id == "pi_testfake"

    # build_zip must have been enqueued
    mock_celery_send_task.assert_called_once_with(
        "tasks.build_zip.build_zip", args=[order.id]
    )


def test_webhook_invalid_signature(client, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake")

    with patch("stripe.Webhook.construct_event", side_effect=stripe.SignatureVerificationError("bad", "sig")):
        resp = client.post(
            "/api/stripe/webhook",
            content=b"{}",
            headers={"stripe-signature": "bad"},
        )
    assert resp.status_code == 400


def test_webhook_invalid_payload_is_generic(client, monkeypatch):
    from photostore.config import settings

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake")

    with patch("stripe.Webhook.construct_event", side_effect=Exception("boom details")):
        resp = client.post(
            "/api/stripe/webhook",
            content=b"{}",
            headers={"stripe-signature": "bad"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Webhook payload invalid"


def test_webhook_idempotent(client, db_session, test_photos, mock_celery_send_task, monkeypatch):
    """Delivering the webhook twice must not re-enqueue build_zip."""
    from photostore.config import settings
    from photostore.models import OrderStatus

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake")

    order = _make_order(db_session, test_photos)

    event_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": order.stripe_session_id,
            "payment_intent": "pi_testfake",
            "customer_email": "runner@example.com",
        }},
    }

    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})
        client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})

    assert mock_celery_send_task.call_count == 1
