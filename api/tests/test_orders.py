from photostore.models import Order, OrderStatus


def _create_order(db_session, status=OrderStatus.PENDING):
    order = Order(
        stripe_session_id=f"cs_test_{status.value}",
        email="runner@example.com",
        status=status,
    )
    db_session.add(order)
    db_session.flush()
    return order


def test_get_order_pending(client, db_session):
    order = _create_order(db_session, OrderStatus.PENDING)
    resp = client.get(f"/api/orders/{order.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PENDING"
    assert data["download_url"] is None


def test_get_order_ready_with_download_url(client, db_session):
    from photostore.models import Delivery
    from datetime import datetime, timedelta, timezone
    import uuid

    order = _create_order(db_session, OrderStatus.READY)
    token = str(uuid.uuid4())
    db_session.add(Delivery(
        order_id=order.id,
        token=token,
        zip_path=f"zips/order-{order.id}.zip",
        event_slug="test-event",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    ))
    db_session.flush()

    resp = client.get(f"/api/orders/{order.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "READY"
    assert f"/d/{token}" in data["download_url"]


def test_get_order_not_found(client):
    resp = client.get("/api/orders/99999")
    assert resp.status_code == 404


def test_stripe_polling_fallback_fulfills_pending_order(
    client, db_session, mock_celery_send_task, monkeypatch
):
    """GET /orders/{id} fulfills a PENDING order when Stripe reports it as paid.

    This covers environments where webhooks cannot reach the server (local dev).
    """
    from unittest.mock import MagicMock, patch
    from photostore.config import settings

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    order = Order(
        stripe_session_id="cs_test_polling_fallback",
        email="runner@example.com",
        status=OrderStatus.PENDING,
    )
    db_session.add(order)
    db_session.flush()

    fake_session = MagicMock()
    fake_session.payment_status = "paid"
    fake_session.payment_intent = "pi_test_polling"
    fake_session.customer_email = "runner@example.com"

    with patch("app.routes.orders.stripe.checkout.Session.retrieve", return_value=fake_session):
        resp = client.get(f"/api/orders/{order.id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == "PAID"

    db_session.refresh(order)
    assert order.status == OrderStatus.PAID
    assert order.stripe_payment_intent_id == "pi_test_polling"
    mock_celery_send_task.assert_called_once_with(
        "tasks.build_zip.build_zip", args=[order.id]
    )


def test_stripe_polling_fallback_skips_placeholder_session(
    client, db_session, monkeypatch
):
    """GET /orders/{id} does NOT call Stripe for placeholder session IDs."""
    from unittest.mock import patch
    from photostore.config import settings

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    order = Order(
        stripe_session_id="pending_some-uuid-here",
        email="runner@example.com",
        status=OrderStatus.PENDING,
    )
    db_session.add(order)
    db_session.flush()

    with patch("app.routes.orders.stripe.checkout.Session.retrieve") as mock_retrieve:
        resp = client.get(f"/api/orders/{order.id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING"
    mock_retrieve.assert_not_called()


def test_stripe_polling_fallback_ignores_unpaid_session(
    client, db_session, monkeypatch
):
    """GET /orders/{id} leaves order PENDING when Stripe session is not yet paid."""
    from unittest.mock import MagicMock, patch
    from photostore.config import settings

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    order = Order(
        stripe_session_id="cs_test_unpaid",
        email="runner@example.com",
        status=OrderStatus.PENDING,
    )
    db_session.add(order)
    db_session.flush()

    fake_session = MagicMock()
    fake_session.payment_status = "unpaid"

    with patch("app.routes.orders.stripe.checkout.Session.retrieve", return_value=fake_session):
        resp = client.get(f"/api/orders/{order.id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING"
