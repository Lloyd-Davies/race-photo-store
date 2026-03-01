import pytest


def test_checkout_stripe_not_configured(client, test_cart):
    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id)})
    assert resp.status_code == 503


def test_checkout_creates_order(client, test_cart, mock_stripe, monkeypatch):
    from unittest.mock import patch

    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ID", "price_fake")

    with patch("app.routes.checkout.stripe.checkout.Session.create", return_value=mock_stripe["session"]) as create_session:
        resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id)})

    assert resp.status_code == 200
    data = resp.json()
    assert "order_id" in data
    assert "order_access_token" in data
    assert data["stripe_checkout_url"] == "https://checkout.stripe.com/test"

    kwargs = create_session.call_args.kwargs
    assert "access_token=" in kwargs["success_url"]


def test_checkout_unknown_cart(client, mock_stripe, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ID", "price_fake")

    import uuid
    resp = client.post("/api/checkout", json={"cart_id": str(uuid.uuid4())})
    assert resp.status_code == 404


def test_checkout_expired_cart(client, db_session, test_cart, mock_stripe, monkeypatch):
    from photostore.config import settings
    from datetime import datetime, timezone

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ID", "price_fake")

    test_cart.expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    db_session.flush()

    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id)})
    assert resp.status_code == 410
