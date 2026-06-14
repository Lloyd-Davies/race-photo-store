import uuid
from datetime import datetime, timedelta, timezone

from photostore.models import DeliveryZipStatus, Order, OrderItem, OrderStatus


def _order_access(order_id: int) -> str:
    from app.order_access import create_order_access_token

    token, _ = create_order_access_token(order_id)
    return token


def _create_order(db_session, status=OrderStatus.PENDING):
    order = Order(
        stripe_session_id=f"cs_test_{status.value}_{uuid.uuid4()}",
        email="runner@example.com",
        status=status,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _add_delivery(db_session, order, token="download-token", **kwargs):
    from photostore.models import Delivery

    delivery = Delivery(
        order_id=order.id,
        token=token,
        zip_path=kwargs.pop("zip_path", None),
        event_slug=kwargs.pop("event_slug", "test-event"),
        expires_at=kwargs.pop(
            "expires_at",
            datetime.now(timezone.utc) + timedelta(days=30),
        ),
        max_downloads=kwargs.pop("max_downloads", 100),
        download_count=kwargs.pop("download_count", 0),
        zip_status=kwargs.pop("zip_status", DeliveryZipStatus.NOT_REQUESTED),
        zip_created_at=kwargs.pop("zip_created_at", None),
        zip_expires_at=kwargs.pop("zip_expires_at", None),
        zip_deleted_at=kwargs.pop("zip_deleted_at", None),
        zip_error=kwargs.pop("zip_error", None),
    )
    db_session.add(delivery)
    db_session.flush()
    return delivery


def test_get_order_pending(client, db_session):
    order = _create_order(db_session, OrderStatus.PENDING)

    resp = client.get(
        f"/api/orders/{order.id}",
        headers={"X-Order-Access": _order_access(order.id)},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PENDING"
    assert data["download_url"] is None
    assert data["zip"]["status"] == "NOT_REQUESTED"
    assert data["items"] == []


def test_get_order_ready_without_zip_has_photo_items(client, db_session, test_photos):
    order = _create_order(db_session, OrderStatus.READY)
    delivery = _add_delivery(db_session, order)
    for photo in test_photos[:2]:
        db_session.add(OrderItem(order_id=order.id, photo_id=photo.id, unit_price_pence=500))
    db_session.flush()

    resp = client.get(
        f"/api/orders/{order.id}",
        headers={"X-Order-Access": _order_access(order.id)},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "READY"
    assert data["download_url"] is None
    assert data["zip"]["status"] == "NOT_REQUESTED"
    assert [item["photo_id"] for item in data["items"]] == [p.id for p in test_photos[:2]]
    assert data["items"][0]["proof_url"].endswith(
        f"/d/{delivery.token}/photos/{test_photos[0].id}/proof"
    )
    assert data["items"][0]["view_url"].endswith(
        f"/d/{delivery.token}/photos/{test_photos[0].id}/view"
    )
    assert data["items"][0]["download_url"].endswith(
        f"/d/{delivery.token}/photos/{test_photos[0].id}"
    )
    assert data["download_items"] == data["items"]


def test_get_order_ready_with_zip_download_url(client, db_session, tmp_path, monkeypatch):
    from photostore.config import settings

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    order = _create_order(db_session, OrderStatus.READY)
    zip_path = tmp_path / "zips" / f"order-{order.id}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(b"PK")
    token = "ready-zip-token"
    _add_delivery(
        db_session,
        order,
        token=token,
        zip_path=f"zips/order-{order.id}.zip",
        zip_status=DeliveryZipStatus.READY,
        zip_created_at=datetime.now(timezone.utc),
        zip_expires_at=datetime.now(timezone.utc) + timedelta(days=3),
    )

    resp = client.get(
        f"/api/orders/{order.id}",
        headers={"X-Order-Access": _order_access(order.id)},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["zip"]["status"] == "READY"
    assert data["zip"]["download_url"].endswith(f"/d/{token}")
    assert data["download_url"].endswith(f"/d/{token}")


def test_prepare_zip_first_call_queues_build(client, db_session, test_photos, mock_celery_send_task):
    order = _create_order(db_session, OrderStatus.READY)
    delivery = _add_delivery(db_session, order)
    db_session.add(OrderItem(order_id=order.id, photo_id=test_photos[0].id, unit_price_pence=500))
    db_session.flush()

    resp = client.post(
        f"/api/orders/{order.id}/zip",
        headers={"X-Order-Access": _order_access(order.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "BUILDING"
    db_session.refresh(delivery)
    assert delivery.zip_status == DeliveryZipStatus.BUILDING
    assert delivery.zip_error is None
    mock_celery_send_task.assert_called_once_with(
        "tasks.build_zip.build_zip",
        args=[order.id],
    )


def test_prepare_zip_ready_does_not_queue_duplicate(
    client,
    db_session,
    tmp_path,
    monkeypatch,
    mock_celery_send_task,
):
    from photostore.config import settings

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    order = _create_order(db_session, OrderStatus.READY)
    zip_path = tmp_path / "zips" / f"order-{order.id}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(b"PK")
    _add_delivery(
        db_session,
        order,
        zip_path=f"zips/order-{order.id}.zip",
        zip_status=DeliveryZipStatus.READY,
        zip_created_at=datetime.now(timezone.utc),
        zip_expires_at=datetime.now(timezone.utc) + timedelta(days=3),
    )

    resp = client.post(
        f"/api/orders/{order.id}/zip",
        headers={"X-Order-Access": _order_access(order.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "READY"
    mock_celery_send_task.assert_not_called()


def test_prepare_zip_failed_allows_retry(client, db_session, mock_celery_send_task):
    order = _create_order(db_session, OrderStatus.READY)
    delivery = _add_delivery(
        db_session,
        order,
        zip_status=DeliveryZipStatus.FAILED,
        zip_error="old failure",
    )

    resp = client.post(
        f"/api/orders/{order.id}/zip",
        headers={"X-Order-Access": _order_access(order.id)},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "BUILDING"
    db_session.refresh(delivery)
    assert delivery.zip_status == DeliveryZipStatus.BUILDING
    assert delivery.zip_error is None
    mock_celery_send_task.assert_called_once_with(
        "tasks.build_zip.build_zip",
        args=[order.id],
    )


def test_get_order_not_found(client):
    resp = client.get("/api/orders/99999", headers={"X-Order-Access": _order_access(99999)})
    assert resp.status_code == 404


def test_get_order_requires_access_token(client, db_session):
    order = _create_order(db_session, OrderStatus.PENDING)
    resp = client.get(f"/api/orders/{order.id}")
    assert resp.status_code == 404


def test_stripe_polling_fallback_fulfills_pending_order(
    client, db_session, mock_celery_send_task, monkeypatch
):
    from unittest.mock import MagicMock, patch
    from photostore.config import settings
    from photostore.models import Delivery

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
        resp = client.get(
            f"/api/orders/{order.id}",
            headers={"X-Order-Access": _order_access(order.id)},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "READY"

    db_session.refresh(order)
    assert order.status == OrderStatus.READY
    assert order.stripe_payment_intent_id == "pi_test_polling"
    delivery = db_session.query(Delivery).filter(Delivery.order_id == order.id).one()
    assert delivery.zip_status == DeliveryZipStatus.NOT_REQUESTED
    mock_celery_send_task.assert_not_called()


def test_stripe_polling_fallback_skips_placeholder_session(
    client, db_session, monkeypatch
):
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
        resp = client.get(
            f"/api/orders/{order.id}",
            headers={"X-Order-Access": _order_access(order.id)},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING"
    mock_retrieve.assert_not_called()


def test_stripe_polling_fallback_ignores_unpaid_session(
    client, db_session, monkeypatch
):
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
        resp = client.get(
            f"/api/orders/{order.id}",
            headers={"X-Order-Access": _order_access(order.id)},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "PENDING"
