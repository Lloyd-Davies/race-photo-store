from datetime import datetime, timezone
from pathlib import Path


# ── Create event ──────────────────────────────────────────────────────────────

def test_create_event(admin_client):
    resp = admin_client.post("/api/admin/events", json={
        "slug": "spring-5k",
        "name": "Spring 5K 2026",
        "date": "2026-03-01T09:00:00Z",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "spring-5k"
    assert "id" in data


def test_create_event_duplicate_slug(admin_client, test_event):
    resp = admin_client.post("/api/admin/events", json={
        "slug": test_event.slug,
        "name": "Duplicate",
        "date": "2026-03-01T09:00:00Z",
    })
    assert resp.status_code == 409


def test_create_event_requires_admin_token(client):
    resp = client.post("/api/admin/events", json={
        "slug": "no-auth",
        "name": "No Auth",
        "date": "2026-03-01T09:00:00Z",
    })
    assert resp.status_code == 401


# ── Ingest ────────────────────────────────────────────────────────────────────

def test_ingest_photos(admin_client, test_event, tmp_path, monkeypatch):
    import os
    from photostore.config import settings

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    for i in range(1, 4):
        pid = f"img-{i:03d}"
        proof = storage / "proofs" / test_event.slug / f"{pid}.jpg"
        original = storage / "originals" / test_event.slug / f"{pid}.jpg"
        proof.parent.mkdir(parents=True, exist_ok=True)
        original.parent.mkdir(parents=True, exist_ok=True)
        proof.write_bytes(b"FAKEJPEG")
        original.write_bytes(b"FAKEJPEG")

    resp = admin_client.post(f"/api/admin/events/{test_event.id}/ingest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ingested"] == 3
    assert data["skipped"] == 0


def test_ingest_skips_existing_photos(admin_client, test_event, test_photos):
    # test_photos fixture monkeypatches STORAGE_ROOT and creates files + DB rows.
    # Calling ingest again should skip all 3 existing photos.
    resp = admin_client.post(f"/api/admin/events/{test_event.id}/ingest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] == 3
    assert data["ingested"] == 0


def test_ingest_unknown_event(admin_client):
    resp = admin_client.post("/api/admin/events/99999/ingest")
    assert resp.status_code == 404


def test_ingest_sets_captured_at_from_exif(admin_client, db_session, test_event, tmp_path, monkeypatch):
    from PIL import Image
    from photostore.config import settings
    from photostore.models import Photo

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    pid = "img-exif-001"
    proof = storage / "proofs" / test_event.slug / f"{pid}.jpg"
    original = storage / "originals" / test_event.slug / f"{pid}.jpg"
    proof.parent.mkdir(parents=True, exist_ok=True)
    original.parent.mkdir(parents=True, exist_ok=True)

    exif = Image.Exif()
    exif[0x9003] = "2026:02:21 09:12:34"  # DateTimeOriginal
    exif[0x0132] = "2026:02:21 09:12:34"  # DateTime

    img = Image.new("RGB", (1000, 800), color=(120, 120, 120))
    img.save(original, format="JPEG", exif=exif.tobytes())
    img.save(proof, format="JPEG", exif=exif.tobytes())

    resp = admin_client.post(f"/api/admin/events/{test_event.id}/ingest")
    assert resp.status_code == 200
    assert resp.json()["ingested"] == 1

    photo = db_session.query(Photo).filter(Photo.id == pid).first()
    assert photo is not None
    assert photo.captured_at is not None
    assert photo.captured_at.hour == 9
    assert photo.captured_at.minute == 12


def test_update_event_fields(admin_client, db_session, test_event):
    from photostore.models import Event

    resp = admin_client.patch(
        f"/api/admin/events/{test_event.id}",
        json={
            "name": "Updated Name",
            "date": "2026-03-02T10:30:00Z",
            "location": "Updated Location",
            "status": "ARCHIVED",
        },
    )
    assert resp.status_code == 200

    refreshed = db_session.query(Event).filter(Event.id == test_event.id).first()
    assert refreshed.name == "Updated Name"
    assert refreshed.location == "Updated Location"
    assert refreshed.status.value == "ARCHIVED"


# ── Bib tags ──────────────────────────────────────────────────────────────────

def test_upload_bib_tags(admin_client, test_event, test_photos):
    resp = admin_client.post(
        f"/api/admin/events/{test_event.id}/tags/bibs",
        json={"tags": [
            {"photo_id": test_photos[0].id, "bib": "42", "confidence": 0.99},
            {"photo_id": test_photos[1].id, "bib": "7",  "confidence": 0.85},
        ]},
    )
    assert resp.status_code == 200
    assert resp.json()["added"] == 2


def test_upload_bib_tags_idempotent(admin_client, test_event, test_photos):
    payload = {"tags": [{"photo_id": test_photos[0].id, "bib": "42", "confidence": 0.99}]}
    admin_client.post(f"/api/admin/events/{test_event.id}/tags/bibs", json=payload)
    resp = admin_client.post(f"/api/admin/events/{test_event.id}/tags/bibs", json=payload)
    assert resp.status_code == 200
    assert resp.json()["added"] == 0  # duplicate, not re-added


# ── Orders management ────────────────────────────────────────────────────────

def _create_ready_order_with_delivery(db_session, test_photos):
    from datetime import timedelta
    import uuid
    from photostore.models import Delivery, Order, OrderItem, OrderStatus

    order = Order(
        stripe_session_id="cs_test_admin_orders",
        email="runner@example.com",
        status=OrderStatus.READY,
    )
    db_session.add(order)
    db_session.flush()

    for photo in test_photos:
        db_session.add(OrderItem(
            order_id=order.id,
            photo_id=photo.id,
            unit_price_pence=500,
        ))

    db_session.add(Delivery(
        order_id=order.id,
        token=str(uuid.uuid4()),
        zip_path=f"zips/order-{order.id}.zip",
        event_slug=test_photos[0].event.slug,
        expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        max_downloads=5,
        download_count=3,
    ))
    db_session.flush()
    return order


def test_admin_list_orders(admin_client, db_session, test_photos):
    order = _create_ready_order_with_delivery(db_session, test_photos)

    resp = admin_client.get("/api/admin/orders")
    assert resp.status_code == 200
    data = resp.json()["orders"]
    assert any(item["id"] == order.id for item in data)


def test_admin_reset_delivery_rotates_and_resets(admin_client, db_session, test_photos):
    from photostore.models import Delivery

    order = _create_ready_order_with_delivery(db_session, test_photos)
    delivery = db_session.query(Delivery).filter(Delivery.order_id == order.id).first()
    old_token = delivery.token

    resp = admin_client.post(
        f"/api/admin/orders/{order.id}/reset-delivery",
        json={"rotate_token": True, "days_valid": 30, "max_downloads": 7},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["download_count"] == 0
    assert data["max_downloads"] == 7
    assert old_token not in data["download_url"]


def test_admin_expire_delivery_sets_status_expired(admin_client, db_session, test_photos):
    from datetime import datetime, timezone
    from photostore.models import Delivery, Order

    order = _create_ready_order_with_delivery(db_session, test_photos)

    resp = admin_client.post(f"/api/admin/orders/{order.id}/expire-delivery")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "EXPIRED"

    delivery = db_session.query(Delivery).filter(Delivery.order_id == order.id).first()
    db_order = db_session.query(Order).filter(Order.id == order.id).first()
    assert delivery.expires_at <= datetime.now(timezone.utc)
    assert db_order.status.value == "EXPIRED"


def test_admin_rebuild_zip_enqueues_and_clears_delivery(
    admin_client,
    db_session,
    test_photos,
    mock_celery_send_task,
):
    from photostore.config import settings
    from photostore.models import Delivery, Order

    order = _create_ready_order_with_delivery(db_session, test_photos)
    delivery = db_session.query(Delivery).filter(Delivery.order_id == order.id).first()

    zip_abs = Path(settings.STORAGE_ROOT) / delivery.zip_path
    zip_abs.parent.mkdir(parents=True, exist_ok=True)
    zip_abs.write_bytes(b"PK")

    resp = admin_client.post(f"/api/admin/orders/{order.id}/rebuild-zip")
    assert resp.status_code == 200
    assert resp.json()["status"] == "PAID"

    remaining = db_session.query(Delivery).filter(Delivery.order_id == order.id).first()
    db_order = db_session.query(Order).filter(Order.id == order.id).first()
    assert remaining is None
    assert db_order.status.value == "PAID"
    assert not zip_abs.exists()

    mock_celery_send_task.assert_called_with("tasks.build_zip.build_zip", args=[order.id])
