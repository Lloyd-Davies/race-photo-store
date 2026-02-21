import uuid
from datetime import datetime, timedelta, timezone

from photostore.models import Delivery, Order, OrderStatus


def _setup_delivery(db_session, tmp_path, max_downloads=5, days_until_expiry=30, download_count=0):
    order = Order(
        stripe_session_id="cs_test_dl",
        email="runner@example.com",
        status=OrderStatus.READY,
    )
    db_session.add(order)
    db_session.flush()

    # Create the actual ZIP file so nginx (mocked here) doesn't need it
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir(parents=True, exist_ok=True)
    (zip_dir / f"order-{order.id}.zip").write_bytes(b"PK")

    token = str(uuid.uuid4())
    delivery = Delivery(
        order_id=order.id,
        token=token,
        zip_path=f"zips/order-{order.id}.zip",
        event_slug="test-event",
        expires_at=datetime.now(timezone.utc) + timedelta(days=days_until_expiry),
        max_downloads=max_downloads,
        download_count=download_count,
    )
    db_session.add(delivery)
    db_session.flush()
    return delivery


def test_download_returns_accel_redirect(client, db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    delivery = _setup_delivery(db_session, tmp_path)
    resp = client.get(f"/d/{delivery.token}")
    assert resp.status_code == 200
    assert "/_internal_zips/" in resp.headers["x-accel-redirect"]
    assert delivery.token  # basic sanity


def test_download_increments_count(client, db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    delivery = _setup_delivery(db_session, tmp_path)
    client.get(f"/d/{delivery.token}")
    db_session.refresh(delivery)
    assert delivery.download_count == 1


def test_download_content_disposition(client, db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    delivery = _setup_delivery(db_session, tmp_path)
    resp = client.get(f"/d/{delivery.token}")
    assert "test-event" in resp.headers["content-disposition"]


def test_download_expired_token(client, db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    delivery = _setup_delivery(db_session, tmp_path, days_until_expiry=-1)
    resp = client.get(f"/d/{delivery.token}")
    assert resp.status_code == 410


def test_download_limit_reached(client, db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    delivery = _setup_delivery(db_session, tmp_path, max_downloads=3, download_count=3)
    resp = client.get(f"/d/{delivery.token}")
    assert resp.status_code == 410


def test_download_unknown_token(client):
    resp = client.get("/d/not-a-real-token")
    assert resp.status_code == 404


def test_download_zip_not_ready_returns_409_and_does_not_increment(
    client, db_session, tmp_path, monkeypatch
):
    from photostore.config import settings

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    delivery = _setup_delivery(db_session, tmp_path)

    zip_path = tmp_path / delivery.zip_path
    zip_path.unlink()

    resp = client.get(f"/d/{delivery.token}")
    assert resp.status_code == 409

    db_session.refresh(delivery)
    assert delivery.download_count == 0
