import json
import hashlib
import hmac
import time
from unittest.mock import call, patch

import stripe


def _post_signed_event(client, payload: dict, secret: str):
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode() + body
    signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return client.post(
        "/api/stripe/webhook",
        content=body,
        headers={"stripe-signature": f"t={timestamp},v1={signature}"},
    )


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


def test_webhook_accepts_realistically_signed_payload(client, db_session, test_photos, monkeypatch):
    from photostore.config import settings
    from photostore.models import OrderStatus, StripeEvent

    secret = "whsec_signed_test"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)
    order = _make_order(db_session, test_photos)
    payload = {
        "id": "evt_signed_valid",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "livemode": True,
        "data": {"object": {
            "id": order.stripe_session_id,
            "object": "checkout.session",
            "payment_intent": "pi_signed_valid",
            "payment_status": "paid",
            "customer_email": order.email,
            "metadata": {"order_id": str(order.id)},
        }},
    }

    resp = _post_signed_event(client, payload, secret)
    duplicate = _post_signed_event(client, payload, secret)

    assert resp.status_code == 200
    assert duplicate.status_code == 200
    db_session.refresh(order)
    assert order.status == OrderStatus.READY
    stored = db_session.query(StripeEvent).filter(
        StripeEvent.stripe_event_id == payload["id"]
    ).one()
    assert stored.processing_status == "PROCESSED"
    assert db_session.query(StripeEvent).filter(
        StripeEvent.stripe_event_id == payload["id"]
    ).count() == 1


def test_webhook_retries_previously_failed_stored_event(
    client, db_session, test_photos, monkeypatch
):
    from photostore.config import settings
    from photostore.models import OrderStatus, StripeEvent

    secret = "whsec_retry_failed"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)
    order = _make_order(db_session, test_photos)
    payload = {
        "id": "evt_retry_failed",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "livemode": True,
        "data": {"object": {
            "id": order.stripe_session_id,
            "object": "checkout.session",
            "payment_intent": "pi_retry_failed",
            "payment_status": "paid",
            "customer_email": order.email,
            "currency": "gbp",
            "amount_subtotal": 1500,
            "amount_total": 1500,
            "total_details": {
                "amount_discount": 0,
                "amount_tax": 0,
                "amount_shipping": 0,
            },
        }},
    }
    db_session.add(StripeEvent(
        stripe_event_id=payload["id"],
        event_type=payload["type"],
        order_id=order.id,
        stripe_session_id=order.stripe_session_id,
        livemode=True,
        payload_json=payload,
        processing_status="FAILED",
        error_message="RuntimeError",
    ))
    db_session.commit()

    resp = _post_signed_event(client, payload, secret)

    assert resp.status_code == 200
    db_session.refresh(order)
    assert order.status == OrderStatus.READY
    assert order.stripe_amount_paid_pence == 1500
    assert order.stripe_pricing_status == "QUEUED"
    stored = db_session.query(StripeEvent).filter(
        StripeEvent.stripe_event_id == payload["id"]
    ).one()
    assert stored.processing_status == "PROCESSED"
    assert stored.error_message is None


def test_webhook_rejects_payload_signed_with_wrong_secret(client, db_session, test_photos, monkeypatch):
    from photostore.config import settings
    from photostore.models import OrderStatus, StripeEvent

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_expected")
    order = _make_order(db_session, test_photos)
    payload = {
        "id": "evt_signed_wrong",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "data": {"object": {"id": order.stripe_session_id}},
    }

    resp = _post_signed_event(client, payload, "whsec_wrong")

    assert resp.status_code == 400
    db_session.refresh(order)
    assert order.status == OrderStatus.PENDING
    assert db_session.query(StripeEvent).filter(
        StripeEvent.stripe_event_id == payload["id"]
    ).count() == 0


def test_webhook_email_enqueue_failure_keeps_order_fulfilled(
    client,
    db_session,
    test_photos,
    mock_celery_send_task,
    monkeypatch,
):
    from photostore.config import settings
    from photostore.models import Communication, CommunicationStatus, OrderActivity, OrderStatus

    secret = "whsec_queue_failure"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    mock_celery_send_task.side_effect = RuntimeError("broker unavailable with private details")
    order = _make_order(db_session, test_photos)
    payload = {
        "id": "evt_queue_failure",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "livemode": True,
        "data": {"object": {
            "id": order.stripe_session_id,
            "object": "checkout.session",
            "payment_intent": "pi_queue_failure",
            "payment_status": "paid",
            "customer_email": order.email,
            "currency": "gbp",
            "amount_subtotal": 1500,
            "amount_total": 1500,
            "total_details": {
                "amount_discount": 0,
                "amount_tax": 0,
                "amount_shipping": 0,
            },
        }},
    }

    resp = _post_signed_event(client, payload, secret)

    assert resp.status_code == 200
    db_session.refresh(order)
    assert order.status == OrderStatus.READY
    assert order.stripe_amount_paid_pence == 1500
    assert order.stripe_pricing_status == "FAILED"
    communication = db_session.query(Communication).filter(
        Communication.order_id == order.id
    ).one()
    assert communication.status == CommunicationStatus.FAILED
    assert communication.error_message == "Email task could not be queued; retry from admin."
    assert "private details" not in communication.error_message
    activity = db_session.query(OrderActivity).filter(
        OrderActivity.order_id == order.id,
        OrderActivity.action == "EMAIL_QUEUE_FAILED",
    ).one()
    assert activity.metadata_json["error_type"] == "RuntimeError"


def test_webhook_persists_authoritative_discounted_pricing(
    client, db_session, test_photos, monkeypatch
):
    from photostore.config import settings
    from photostore.models import OrderDiscount

    secret = "whsec_discounted"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)
    order = _make_order(db_session, test_photos)
    payload = {
        "id": "evt_discounted",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "data": {"object": {
            "id": order.stripe_session_id,
            "object": "checkout.session",
            "payment_intent": "pi_discounted",
            "payment_status": "paid",
            "currency": "gbp",
            "amount_subtotal": 1500,
            "amount_total": 1200,
            "total_details": {
                "amount_discount": 300,
                "amount_tax": 0,
                "amount_shipping": 0,
                "breakdown": {"discounts": [{
                    "amount": 300,
                    "discount": {"id": "di_discounted", "promotion_code": "promo_123"},
                }]},
            },
            "discounts": [{"id": "di_discounted", "promotion_code": "promo_123"}],
        }},
    }

    resp = _post_signed_event(client, payload, secret)

    assert resp.status_code == 200
    db_session.refresh(order)
    assert order.stripe_amount_subtotal_pence == 1500
    assert order.stripe_discount_pence == 300
    assert order.stripe_amount_paid_pence == 1200
    assert order.currency == "GBP"
    discount = db_session.query(OrderDiscount).filter(OrderDiscount.order_id == order.id).one()
    assert discount.stripe_promotion_code_id == "promo_123"
    assert discount.amount_pence == 300


def test_webhook_refund_updates_order_idempotently(
    client, db_session, test_photos, monkeypatch
):
    from photostore.config import settings
    from photostore.models import OrderRefund

    secret = "whsec_refund"
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", secret)
    order = _make_order(db_session, test_photos)
    order.stripe_payment_intent_id = "pi_refund"
    order.stripe_amount_paid_pence = 1500
    db_session.commit()
    payload = {
        "id": "evt_refund",
        "object": "event",
        "type": "refund.updated",
        "created": int(time.time()),
        "data": {"object": {
            "id": "re_refund",
            "object": "refund",
            "payment_intent": "pi_refund",
            "amount": 500,
            "currency": "gbp",
            "status": "succeeded",
            "created": int(time.time()),
        }},
    }

    first = _post_signed_event(client, payload, secret)
    duplicate = _post_signed_event(client, payload, secret)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    db_session.refresh(order)
    assert order.stripe_amount_refunded_pence == 500
    assert db_session.query(OrderRefund).filter(OrderRefund.order_id == order.id).count() == 1


def test_webhook_fulfills_order(client, db_session, test_photos, mock_celery_send_task, monkeypatch):
    from photostore.config import settings
    from photostore.models import Delivery, DeliveryZipStatus, OrderStatus

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
    assert order.status == OrderStatus.READY
    assert order.stripe_payment_intent_id == "pi_testfake"

    delivery = db_session.query(Delivery).filter(Delivery.order_id == order.id).one()
    assert delivery.zip_path is None
    assert delivery.zip_status == DeliveryZipStatus.NOT_REQUESTED
    mock_celery_send_task.assert_not_called()


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
    """Delivering the webhook twice must not enqueue ZIP work."""
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

    assert mock_celery_send_task.call_count == 0


def test_webhook_persists_stripe_event_once(client, db_session, test_photos, monkeypatch):
    from photostore.config import settings
    from photostore.models import StripeEvent

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake")
    order = _make_order(db_session, test_photos)
    event_payload = {
        "id": "evt_test_persisted",
        "type": "checkout.session.completed",
        "created": 1800000000,
        "livemode": False,
        "data": {"object": {
            "id": order.stripe_session_id,
            "payment_intent": "pi_persisted",
            "customer_email": "runner@example.com",
        }},
    }

    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})
        client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})

    events = db_session.query(StripeEvent).filter(
        StripeEvent.stripe_event_id == "evt_test_persisted"
    ).all()
    assert len(events) == 1
    assert events[0].processing_status == "PROCESSED"
    assert events[0].order_id == order.id


def test_webhook_queues_download_ready_email(client, db_session, test_photos, mock_celery_send_task, monkeypatch):
    """After payment, a DOWNLOAD_READY send_email task must be enqueued exactly once."""
    from photostore.config import settings
    from photostore.models import Communication, CommunicationKind

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)

    order = _make_order(db_session, test_photos)

    event_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": order.stripe_session_id,
            "payment_intent": "pi_email_test",
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

    # A communication row should exist
    comm = (
        db_session.query(Communication)
        .filter(Communication.order_id == order.id)
        .filter(Communication.kind == CommunicationKind.DOWNLOAD_READY)
        .first()
    )
    assert comm is not None, "Communication row was not created"

    # The send_email task should have been called with the communication id
    send_email_calls = [
        c for c in mock_celery_send_task.call_args_list
        if c.args and c.args[0] == "tasks.send_email.send_email"
    ]
    assert len(send_email_calls) == 1
    assert send_email_calls[0].kwargs["args"] == [comm.id]


def test_webhook_duplicate_does_not_queue_second_email(client, db_session, test_photos, mock_celery_send_task, monkeypatch):
    """Second identical webhook must not enqueue a second DOWNLOAD_READY email."""
    from photostore.config import settings
    from photostore.models import Communication

    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_fake")
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)

    order = _make_order(db_session, test_photos)

    event_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": order.stripe_session_id,
            "payment_intent": "pi_dup_test",
            "customer_email": "runner@example.com",
        }},
    }

    with patch("stripe.Webhook.construct_event", return_value=event_payload):
        client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})
        client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})

    send_email_calls = [
        c for c in mock_celery_send_task.call_args_list
        if c.args and c.args[0] == "tasks.send_email.send_email"
    ]
    assert len(send_email_calls) == 1

    comm_count = (
        db_session.query(Communication)
        .filter(Communication.order_id == order.id)
        .count()
    )
    assert comm_count == 1
