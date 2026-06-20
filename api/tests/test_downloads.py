import uuid
from datetime import datetime, timedelta, timezone

from photostore.models import Delivery, DeliveryZipStatus, Order, OrderItem, OrderStatus


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
        zip_status=DeliveryZipStatus.READY,
        zip_created_at=datetime.now(timezone.utc),
        zip_expires_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db_session.add(delivery)
    db_session.flush()
    return delivery


def _setup_photo_delivery(
    db_session,
    test_photos,
    max_downloads=5,
    days_until_expiry=30,
    download_count=0,
):
    order = Order(
        stripe_session_id=f"cs_test_photo_dl_{uuid.uuid4()}",
        email="runner@example.com",
        status=OrderStatus.READY,
    )
    db_session.add(order)
    db_session.flush()

    purchased = test_photos[:2]
    for photo in purchased:
        db_session.add(
            OrderItem(order_id=order.id, photo_id=photo.id, unit_price_pence=500)
        )

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
    return delivery, purchased


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


def test_download_redirects_to_presigned_url_for_r2_backend(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    from app.routes import downloads as downloads_module

    class FakeR2Storage:
        is_local = False

        def __init__(self):
            self.presigned_key = None

        def exists(self, key):
            return True

        def presigned_get_url(
            self,
            key,
            expires_seconds=3600,
            response_content_disposition=None,
            response_content_type=None,
        ):
            self.presigned_key = key
            self.disposition = response_content_disposition
            self.content_type = response_content_type
            return (
                f"https://r2.example.test/{key}?signature=test"
                f"&disposition={response_content_disposition}"
                f"&content_type={response_content_type}"
            )

    storage = FakeR2Storage()
    monkeypatch.setattr(downloads_module, "get_zip_storage_backend", lambda: storage)
    delivery = _setup_delivery(db_session, tmp_path)

    resp = client.get(f"/d/{delivery.token}", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"].startswith(
        f"https://r2.example.test/zips/order-{delivery.order_id}.zip?signature=test"
    )
    assert "x-accel-redirect" not in resp.headers
    assert storage.presigned_key == f"zips/order-{delivery.order_id}.zip"
    assert storage.disposition == (
        f'attachment; filename="event-test-event-order-{delivery.order_id}.zip"'
    )
    assert storage.content_type == "application/zip"
    db_session.refresh(delivery)
    assert delivery.download_count == 1


def test_download_missing_r2_zip_marks_expired_without_incrementing(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    from app.routes import downloads as downloads_module

    class MissingR2Storage:
        is_local = False

        def exists(self, key):
            return False

    monkeypatch.setattr(downloads_module, "get_zip_storage_backend", lambda: MissingR2Storage())
    delivery = _setup_delivery(db_session, tmp_path)

    resp = client.get(f"/d/{delivery.token}", follow_redirects=False)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "ZIP has expired. Regenerate it from the order page."
    db_session.refresh(delivery)
    assert delivery.download_count == 0
    assert delivery.zip_status == DeliveryZipStatus.EXPIRED
    assert delivery.zip_deleted_at is not None


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
    assert delivery.zip_status == DeliveryZipStatus.EXPIRED


def test_download_zip_not_requested_returns_409(client, db_session, tmp_path, monkeypatch):
    from photostore.config import settings

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    delivery = _setup_delivery(db_session, tmp_path)
    delivery.zip_status = DeliveryZipStatus.NOT_REQUESTED
    delivery.zip_path = None
    db_session.flush()

    resp = client.get(f"/d/{delivery.token}")

    assert resp.status_code == 409
    assert resp.json()["detail"] == "ZIP has not been prepared"


def test_download_zip_building_returns_202(client, db_session, tmp_path, monkeypatch):
    from photostore.config import settings

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    delivery = _setup_delivery(db_session, tmp_path)
    delivery.zip_status = DeliveryZipStatus.BUILDING
    db_session.flush()

    resp = client.get(f"/d/{delivery.token}")

    assert resp.status_code == 202
    assert resp.json()["detail"] == "ZIP is being prepared"


def test_photo_download_returns_accel_redirect_and_does_not_increment(
    client, db_session, test_photos
):
    delivery, purchased = _setup_photo_delivery(db_session, test_photos)

    resp = client.get(f"/d/{delivery.token}/photos/{purchased[0].id}")

    assert resp.status_code == 200
    assert resp.headers["x-accel-redirect"].endswith(
        f"/test-event/{purchased[0].id}.jpg"
    )
    assert resp.headers["content-type"] == "image/jpeg"
    assert "attachment" in resp.headers["content-disposition"]
    assert purchased[0].id in resp.headers["content-disposition"]

    db_session.refresh(delivery)
    assert delivery.download_count == 0


def test_photo_download_rejects_unknown_token(client, test_photos):
    resp = client.get(f"/d/not-a-real-token/photos/{test_photos[0].id}")
    assert resp.status_code == 404


def test_photo_download_rejects_expired_token(client, db_session, test_photos):
    delivery, purchased = _setup_photo_delivery(
        db_session,
        test_photos,
        days_until_expiry=-1,
    )

    resp = client.get(f"/d/{delivery.token}/photos/{purchased[0].id}")

    assert resp.status_code == 410


def test_photo_download_ignores_zip_download_limit(
    client, db_session, test_photos
):
    delivery, purchased = _setup_photo_delivery(
        db_session,
        test_photos,
        max_downloads=3,
        download_count=3,
    )

    resp = client.get(f"/d/{delivery.token}/photos/{purchased[0].id}")

    assert resp.status_code == 200
    db_session.refresh(delivery)
    assert delivery.download_count == 3


def test_photo_download_rejects_photo_not_purchased(
    client, db_session, test_photos
):
    delivery, _ = _setup_photo_delivery(db_session, test_photos)

    resp = client.get(f"/d/{delivery.token}/photos/{test_photos[2].id}")

    assert resp.status_code == 404


def test_photo_download_missing_original_returns_404(client, db_session, test_photos):
    from pathlib import Path
    from photostore.config import settings

    delivery, purchased = _setup_photo_delivery(db_session, test_photos)
    original = Path(settings.STORAGE_ROOT) / purchased[0].original_path
    original.unlink()

    resp = client.get(f"/d/{delivery.token}/photos/{purchased[0].id}")

    assert resp.status_code == 404


def test_photo_proof_download_returns_accel_redirect(client, db_session, test_photos):
    delivery, purchased = _setup_photo_delivery(db_session, test_photos)

    resp = client.get(f"/d/{delivery.token}/photos/{purchased[0].id}/proof")

    assert resp.status_code == 200
    assert resp.headers["x-accel-redirect"].endswith(
        f"/test-event/{purchased[0].id}.jpg"
    )
    assert resp.headers["content-type"] == "image/jpeg"


def test_photo_view_returns_inline_original(client, db_session, test_photos):
    delivery, purchased = _setup_photo_delivery(db_session, test_photos)

    resp = client.get(f"/d/{delivery.token}/photos/{purchased[0].id}/view")

    assert resp.status_code == 200
    assert resp.headers["x-accel-redirect"].endswith(
        f"/test-event/{purchased[0].id}.jpg"
    )
    assert resp.headers["content-type"] == "image/jpeg"
    assert "inline" in resp.headers["content-disposition"]
