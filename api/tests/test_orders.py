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
