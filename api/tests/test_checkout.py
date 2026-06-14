def test_checkout_stripe_not_configured(client, test_cart):
    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})
    assert resp.status_code == 503


def test_free_checkout_does_not_require_stripe(
    client, db_session, test_cart, test_event, mock_stripe, mock_celery_send_task
):
    from photostore.models import Delivery, DeliveryZipStatus, Order, OrderItem, OrderStatus

    test_event.photo_price_pence = 0
    db_session.flush()

    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["stripe_checkout_url"] is None
    assert data["order_access_token"]

    order = db_session.query(Order).filter(Order.id == data["order_id"]).one()
    assert order.status == OrderStatus.READY
    assert order.paid_at is not None
    assert order.stripe_session_id.startswith("free_")
    assert {
        row[0]
        for row in db_session.query(OrderItem.unit_price_pence)
        .filter(OrderItem.order_id == order.id)
        .all()
    } == {0}
    delivery = db_session.query(Delivery).filter(Delivery.order_id == order.id).one()
    assert delivery.zip_path is None
    assert delivery.zip_status == DeliveryZipStatus.NOT_REQUESTED
    mock_celery_send_task.assert_not_called()


def test_checkout_creates_order(client, test_cart, mock_stripe, monkeypatch):
    from unittest.mock import patch

    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    with patch("app.routes.checkout.stripe.checkout.Session.create", return_value=mock_stripe["session"]) as create_session:
        resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})

    assert resp.status_code == 200
    data = resp.json()
    assert "order_id" in data
    assert "order_access_token" in data
    assert data["stripe_checkout_url"] == "https://checkout.stripe.com/test"

    kwargs = create_session.call_args.kwargs
    assert "access_token=" in kwargs["success_url"]
    line_item = kwargs["line_items"][0]
    assert line_item["price_data"]["unit_amount"] == 500
    assert line_item["price_data"]["currency"] == "gbp"
    assert "price" not in line_item


def test_checkout_unknown_cart(client, mock_stripe, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    import uuid
    resp = client.post("/api/checkout", json={"cart_id": str(uuid.uuid4()), "email": "runner@example.com"})
    assert resp.status_code == 404


def test_checkout_expired_cart(client, db_session, test_cart, mock_stripe, monkeypatch):
    from photostore.config import settings
    from datetime import datetime, timezone

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    test_cart.expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    db_session.flush()

    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})
    assert resp.status_code == 410


def test_checkout_requires_email_when_order_email_required(client, test_cart, mock_stripe, monkeypatch):
    """When ORDER_EMAIL_REQUIRED=True, omitting email should return 422."""
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "ORDER_EMAIL_REQUIRED", True)

    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id)})
    assert resp.status_code == 422


def test_checkout_accepts_empty_email_when_not_required(client, test_cart, mock_stripe, monkeypatch):
    """When ORDER_EMAIL_REQUIRED=False, omitting email should still succeed."""
    from unittest.mock import patch
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "ORDER_EMAIL_REQUIRED", False)

    with patch("app.routes.checkout.stripe.checkout.Session.create", return_value=mock_stripe["session"]):
        resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id)})

    assert resp.status_code == 200


def test_checkout_rejects_invalid_email_format(client, test_cart, mock_stripe, monkeypatch):
    """A malformed email address must be rejected regardless of ORDER_EMAIL_REQUIRED."""
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")

    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "not-an-email"})
    assert resp.status_code == 422


def test_checkout_uses_event_price_override_and_snapshots_order_items(
    client, db_session, test_cart, test_event, mock_stripe, monkeypatch
):
    from unittest.mock import patch
    from photostore.config import settings
    from photostore.models import Order, OrderItem

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    test_event.photo_price_pence = 725
    db_session.flush()

    with patch("app.routes.checkout.stripe.checkout.Session.create", return_value=mock_stripe["session"]) as create_session:
        resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})

    assert resp.status_code == 200
    kwargs = create_session.call_args.kwargs
    assert kwargs["line_items"][0]["price_data"]["unit_amount"] == 725

    order = db_session.query(Order).filter(Order.id == resp.json()["order_id"]).one()
    assert order.currency == "GBP"
    item_prices = {
        row[0]
        for row in db_session.query(OrderItem.unit_price_pence)
        .filter(OrderItem.order_id == order.id)
        .all()
    }
    assert item_prices == {725}


def test_checkout_passes_stripe_promotion_code_toggle(
    client, db_session, test_cart, mock_stripe, monkeypatch
):
    from unittest.mock import patch
    from photostore.config import settings
    from photostore.pricing import get_app_settings

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    app_settings = get_app_settings(db_session)
    app_settings.allow_stripe_promotion_codes = True
    db_session.flush()

    with patch("app.routes.checkout.stripe.checkout.Session.create", return_value=mock_stripe["session"]) as create_session:
        resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})

    assert resp.status_code == 200
    assert create_session.call_args.kwargs["allow_promotion_codes"] is True

