import pytest


def test_checkout_stripe_not_configured(client, test_cart):
    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})
    assert resp.status_code == 503


def test_checkout_creates_order(client, test_cart, mock_stripe, monkeypatch):
    from unittest.mock import patch

    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ID", "price_fake")

    with patch("app.routes.checkout.stripe.checkout.Session.create", return_value=mock_stripe["session"]) as create_session:
        resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})

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
    resp = client.post("/api/checkout", json={"cart_id": str(uuid.uuid4()), "email": "runner@example.com"})
    assert resp.status_code == 404


def test_checkout_expired_cart(client, db_session, test_cart, mock_stripe, monkeypatch):
    from photostore.config import settings
    from datetime import datetime, timezone

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ID", "price_fake")

    test_cart.expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    db_session.flush()

    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "runner@example.com"})
    assert resp.status_code == 410


def test_checkout_requires_email_when_order_email_required(client, test_cart, mock_stripe, monkeypatch):
    """When ORDER_EMAIL_REQUIRED=True, omitting email should return 422."""
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ID", "price_fake")
    monkeypatch.setattr(settings, "ORDER_EMAIL_REQUIRED", True)

    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id)})
    assert resp.status_code == 422


def test_checkout_accepts_empty_email_when_not_required(client, test_cart, mock_stripe, monkeypatch):
    """When ORDER_EMAIL_REQUIRED=False, omitting email should still succeed."""
    from unittest.mock import patch
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ID", "price_fake")
    monkeypatch.setattr(settings, "ORDER_EMAIL_REQUIRED", False)

    with patch("app.routes.checkout.stripe.checkout.Session.create", return_value=mock_stripe["session"]):
        resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id)})

    assert resp.status_code == 200


def test_checkout_rejects_invalid_email_format(client, test_cart, mock_stripe, monkeypatch):
    """A malformed email address must be rejected regardless of ORDER_EMAIL_REQUIRED."""
    from photostore.config import settings
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(settings, "STRIPE_PRICE_ID", "price_fake")

    resp = client.post("/api/checkout", json={"cart_id": str(test_cart.id), "email": "not-an-email"})
    assert resp.status_code == 422

