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


def test_create_protected_event_requires_password(admin_client):
    resp = admin_client.post("/api/admin/events", json={
        "slug": "locked-without-password",
        "name": "Locked Event",
        "date": "2026-03-01T09:00:00Z",
        "is_password_protected": True,
    })
    assert resp.status_code == 400


def test_create_protected_event_sets_password_hash(admin_client, db_session):
    from photostore.models import Event

    resp = admin_client.post("/api/admin/events", json={
        "slug": "locked-with-password",
        "name": "Locked Event",
        "date": "2026-03-01T09:00:00Z",
        "is_password_protected": True,
        "access_password": "secret123",
        "access_hint": "Club code",
    })
    assert resp.status_code == 200

    created_id = resp.json()["id"]
    event = db_session.query(Event).filter(Event.id == created_id).first()
    assert event is not None
    assert event.is_password_protected is True
    assert event.access_password_hash is not None
    assert event.access_hint == "Club code"


def test_create_protected_event_sets_secret_hash(admin_client, db_session):
    from photostore.models import Event

    resp = admin_client.post("/api/admin/events", json={
        "slug": "locked-with-secret",
        "name": "Locked Event Secret",
        "date": "2026-03-01T09:00:00Z",
        "is_password_protected": True,
        "access_secret": "event-secret-123",
        "access_hint": "Team code",
    })
    assert resp.status_code == 200

    created_id = resp.json()["id"]
    event = db_session.query(Event).filter(Event.id == created_id).first()
    assert event is not None
    assert event.is_password_protected is True
    assert event.access_password_hash is not None


def test_admin_session_valid(admin_client):
    resp = admin_client.get("/api/admin/session")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_admin_login_issues_tokens(client):
    resp = client.post("/api/admin/login", json={"admin_token": "test-admin-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["access_expires_at"]
    assert data["refresh_expires_at"]


def test_admin_login_rejects_invalid_token(client):
    resp = client.post("/api/admin/login", json={"admin_token": "wrong-token"})
    assert resp.status_code == 401


def test_admin_refresh_rotates_session(client):
    login = client.post("/api/admin/login", json={"admin_token": "test-admin-token"})
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    refresh = client.post("/api/admin/refresh", json={"refresh_token": refresh_token})
    assert refresh.status_code == 200
    data = refresh.json()
    assert data["access_token"]
    assert data["refresh_token"]

    session = client.get(
        "/api/admin/session",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert session.status_code == 200


def test_admin_session_requires_admin_token(client):
    resp = client.get("/api/admin/session")
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


def test_update_event_protection_requires_password(admin_client, test_event):
    resp = admin_client.patch(
        f"/api/admin/events/{test_event.id}",
        json={"is_password_protected": True},
    )
    assert resp.status_code == 400


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


def test_upload_bib_tags_rejects_unknown_photo_ids(admin_client, test_event):
    resp = admin_client.post(
        f"/api/admin/events/{test_event.id}/tags/bibs",
        json={
            "tags": [
                {"photo_id": "missing-photo-001", "bib": "457", "confidence": 0.95},
            ],
        },
    )
    assert resp.status_code == 400
    assert "not found in this event" in str(resp.json().get("detail", "")).lower()


def test_upload_bib_tags_trims_and_deduplicates_equivalent_values(admin_client, db_session, test_event, test_photos):
    from photostore.models import PhotoTag

    first = {
        "tags": [{"photo_id": test_photos[0].id, "bib": " 0042 ", "confidence": 0.99}],
    }
    second = {
        "tags": [{"photo_id": test_photos[0].id, "bib": "0042", "confidence": 0.90}],
    }

    r1 = admin_client.post(f"/api/admin/events/{test_event.id}/tags/bibs", json=first)
    assert r1.status_code == 200
    assert r1.json()["added"] == 1

    r2 = admin_client.post(f"/api/admin/events/{test_event.id}/tags/bibs", json=second)
    assert r2.status_code == 200
    assert r2.json()["added"] == 0

    tag = db_session.query(PhotoTag).filter(
        PhotoTag.photo_id == test_photos[0].id,
        PhotoTag.tag_type == "bib",
    ).one()
    assert tag.value == "0042"


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


# ── Admin events list (S2) ────────────────────────────────────────────────────

def test_list_admin_events_returns_all_statuses(admin_client, db_session, test_event):
    from photostore.models import Event, EventStatus

    archived = Event(
        slug="archived-5k",
        name="Old Race",
        date="2024-01-01T09:00:00Z",
        status=EventStatus.ARCHIVED,
    )
    db_session.add(archived)
    db_session.flush()

    resp = admin_client.get("/api/admin/events")
    assert resp.status_code == 200
    slugs = [e["slug"] for e in resp.json()]
    assert test_event.slug in slugs
    assert "archived-5k" in slugs


def test_list_admin_events_requires_admin(client):
    resp = client.get("/api/admin/events")
    assert resp.status_code == 401


# ── Photo IDs endpoint (S3) ───────────────────────────────────────────────────

def test_get_photo_ids(admin_client, test_event, test_photos):
    resp = admin_client.get(f"/api/admin/events/{test_event.id}/photo_ids")
    assert resp.status_code == 200
    data = resp.json()
    assert "photo_ids" in data
    assert set(data["photo_ids"]) == {p.id for p in test_photos}


def test_get_photo_ids_empty_event(admin_client, test_event):
    resp = admin_client.get(f"/api/admin/events/{test_event.id}/photo_ids")
    assert resp.status_code == 200
    assert resp.json()["photo_ids"] == []


def test_get_photo_ids_unknown_event(admin_client):
    resp = admin_client.get("/api/admin/events/99999/photo_ids")
    assert resp.status_code == 404


# ── Delete event endpoint (S4) ────────────────────────────────────────────────

def test_delete_event_removes_photos_and_tags(admin_client, db_session, test_event, test_photos):
    from photostore.models import Event, Photo, PhotoTag

    # Add a bib tag
    db_session.add(PhotoTag(photo_id=test_photos[0].id, tag_type="bib", value="42", confidence=0.9))
    db_session.flush()

    resp = admin_client.delete(f"/api/admin/events/{test_event.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["photos_deleted"] == 3
    assert data["tags_deleted"] == 1
    assert data["orders_affected"] == 0
    assert data["files_deleted"] is False

    assert db_session.query(Event).filter(Event.id == test_event.id).first() is None
    assert db_session.query(Photo).filter(Photo.event_id == test_event.id).count() == 0


def test_delete_event_blocked_by_paid_orders(admin_client, db_session, test_event, test_photos):
    from photostore.models import Order, OrderItem, OrderStatus

    order = Order(
        stripe_session_id="cs_block_delete",
        email="a@b.com",
        status=OrderStatus.PAID,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderItem(order_id=order.id, photo_id=test_photos[0].id, unit_price_pence=500))
    db_session.flush()

    resp = admin_client.delete(f"/api/admin/events/{test_event.id}")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["orders_affected"] == 1
    assert "1 paid order" in detail["message"]


def test_delete_event_force_overrides_paid_orders(admin_client, db_session, test_event, test_photos):
    from photostore.models import Event, Order, OrderItem, OrderStatus

    order = Order(
        stripe_session_id="cs_force_delete",
        email="a@b.com",
        status=OrderStatus.PAID,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderItem(order_id=order.id, photo_id=test_photos[0].id, unit_price_pence=500))
    db_session.flush()

    resp = admin_client.delete(f"/api/admin/events/{test_event.id}?force=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["orders_affected"] == 1
    assert db_session.query(Event).filter(Event.id == test_event.id).first() is None


def test_delete_event_with_files(admin_client, db_session, test_event, test_photos, tmp_path, monkeypatch):
    from photostore.config import settings

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    for kind in ("proofs", "originals"):
        d = storage / kind / test_event.slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "test.jpg").write_bytes(b"x")

    resp = admin_client.delete(f"/api/admin/events/{test_event.id}?delete_files=true")
    assert resp.status_code == 200
    assert resp.json()["files_deleted"] is True
    assert not (storage / "proofs" / test_event.slug).exists()
    assert not (storage / "originals" / test_event.slug).exists()


def test_delete_event_unknown(admin_client):
    resp = admin_client.delete("/api/admin/events/99999")
    assert resp.status_code == 404


# ── upload_photo ─────────────────────────────────────────────────────────────

def _upload(client, event_id: int, photo_id: str, kind: str, data: bytes = b"\xff\xd8\xff\xe0test"):
    return client.post(
        f"/api/admin/events/{event_id}/photos",
        data={"photo_id": photo_id, "kind": kind},
        files={"file": ("photo.jpg", data, "image/jpeg")},
    )


def test_upload_photo_invalid_kind(admin_client, test_event):
    resp = _upload(admin_client, test_event.id, "photo_001", "thumbnail")
    assert resp.status_code == 400
    assert "kind" in resp.json()["detail"].lower()


def test_upload_photo_invalid_photo_id(admin_client, test_event):
    resp = _upload(admin_client, test_event.id, "../evil", "proof")
    assert resp.status_code == 400
    assert "photo_id" in resp.json()["detail"].lower()


def test_upload_photo_proof_creates_record(admin_client, db_session, test_event, tmp_path, monkeypatch):
    import os

    from photostore.config import settings
    from photostore.models import Photo

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    resp = _upload(admin_client, test_event.id, "img_001", "proof")
    assert resp.status_code == 200
    data = resp.json()
    assert data["photo_id"] == "img_001"
    assert data["kind"] == "proof"
    assert data["created"] is True
    assert data["size_bytes"] > 0

    photo = db_session.query(Photo).filter(Photo.id == "img_001").first()
    assert photo is not None
    assert photo.proof_path == f"proofs/{test_event.slug}/img_001.jpg"
    proof_path = storage / "proofs" / test_event.slug / "img_001.jpg"
    assert proof_path.exists()

    if os.name != "nt":
        mode = proof_path.stat().st_mode & 0o777
        assert mode == 0o644


def test_upload_photo_original_creates_record(admin_client, db_session, test_event, tmp_path, monkeypatch):
    from photostore.config import settings
    from photostore.models import Photo, PhotoState

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    resp = _upload(admin_client, test_event.id, "img_002", "original")
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] is True

    photo = db_session.query(Photo).filter(Photo.id == "img_002").first()
    assert photo is not None
    assert photo.original_path == f"originals/{test_event.slug}/img_002.jpg"
    assert photo.state == PhotoState.READY
    assert (storage / "originals" / test_event.slug / "img_002.jpg").exists()


def test_upload_photo_updates_existing(admin_client, db_session, test_event, test_photos, tmp_path, monkeypatch):
    from photostore.config import settings
    from photostore.models import Photo

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    existing_id = test_photos[0].id
    resp = _upload(admin_client, test_event.id, existing_id, "proof")
    assert resp.status_code == 200
    assert resp.json()["created"] is False

    db_session.expire_all()
    photo = db_session.query(Photo).filter(Photo.id == existing_id).first()
    assert photo.proof_path == f"proofs/{test_event.slug}/{existing_id}.jpg"


def test_upload_photo_unknown_event(admin_client):
    resp = _upload(admin_client, 99999, "img_003", "proof")
    assert resp.status_code == 404


def test_upload_photo_cross_event_collision(admin_client, db_session, test_event, tmp_path, monkeypatch):
    """Uploading a photo_id that already belongs to a different event must return 409."""
    from photostore.config import settings
    from photostore.models import Event, Photo, PhotoState

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    other_event = Event(slug="other-race", name="Other Race", date="2025-06-01T09:00:00Z")
    db_session.add(other_event)
    db_session.flush()

    # Create a photo belonging to other_event
    db_session.add(Photo(
        id="shared_001",
        event_id=other_event.id,
        proof_path=f"proofs/other-race/shared_001.jpg",
        original_path=f"originals/other-race/shared_001.jpg",
        state=PhotoState.MISSING,
    ))
    db_session.flush()

    # Attempt to upload under test_event using the same photo_id
    resp = _upload(admin_client, test_event.id, "shared_001", "proof")
    assert resp.status_code == 409
    assert "different event" in resp.json()["detail"]


def test_upload_photo_rejects_oversized_file(admin_client, db_session, test_event, tmp_path, monkeypatch):
    from photostore.config import settings
    from photostore.models import Photo

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(settings, "MAX_PHOTO_UPLOAD_BYTES", 8)

    resp = _upload(admin_client, test_event.id, "too_big_001", "proof", data=b"0123456789")
    assert resp.status_code == 413
    assert "exceeds max size" in resp.json()["detail"]

    photo = db_session.query(Photo).filter(Photo.id == "too_big_001").first()
    assert photo is None
    assert not (storage / "proofs" / test_event.slug / "too_big_001.jpg").exists()


# ── Bib tag replace flag ──────────────────────────────────────────────────────

def test_upload_bib_tags_replace_clears_existing(admin_client, db_session, test_event, test_photos):
    from photostore.models import PhotoTag

    photo_id = test_photos[0].id

    # Seed an existing bib tag
    db_session.add(PhotoTag(photo_id=photo_id, tag_type="bib", value="old_bib", confidence=0.9))
    db_session.flush()

    # Upload with replace=True — should wipe old tags and add the new one
    resp = admin_client.post(
        f"/api/admin/events/{test_event.id}/tags/bibs",
        json={
            "tags": [{"photo_id": photo_id, "bib": "new_bib", "confidence": 0.95}],
            "replace": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["added"] == 1

    tags = db_session.query(PhotoTag).filter(PhotoTag.photo_id == photo_id, PhotoTag.tag_type == "bib").all()
    assert len(tags) == 1
    assert tags[0].value == "new_bib"


# ── Communication history + resend ───────────────────────────────────────────

def _create_order_with_communication(db_session, test_photos, kind="ORDER_CONFIRMED"):
    """Seed an order with one Communication row of the given kind."""
    import uuid
    from datetime import timedelta
    from photostore.models import (
        Communication, CommunicationKind, CommunicationStatus,
        Delivery, Order, OrderItem, OrderStatus,
    )

    order = Order(
        stripe_session_id=f"cs_test_comms_{kind}_{uuid.uuid4().hex[:6]}",
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
        download_count=0,
    ))

    comm = Communication(
        order_id=order.id,
        kind=CommunicationKind(kind),
        status=CommunicationStatus.SENT,
        provider="brevo",
        recipient_email=order.email,
        subject="Your order is confirmed",
        template_key=kind,
        initiated_by="system",
        dedupe_key=f"{kind.lower()}:{order.id}",
    )
    db_session.add(comm)
    db_session.flush()
    return order, comm


def test_admin_list_communications_empty(admin_client, db_session, test_photos):
    order = _create_ready_order_with_delivery(db_session, test_photos)

    resp = admin_client.get(f"/api/admin/orders/{order.id}/communications")
    assert resp.status_code == 200
    assert resp.json() == []


def test_admin_list_communications_returns_history(admin_client, db_session, test_photos):
    order, comm = _create_order_with_communication(db_session, test_photos)

    resp = admin_client.get(f"/api/admin/orders/{order.id}/communications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == comm.id
    assert data[0]["kind"] == "ORDER_CONFIRMED"
    assert data[0]["status"] == "SENT"
    assert data[0]["recipient_email"] == "runner@example.com"


def test_admin_list_communications_order_not_found(admin_client):
    resp = admin_client.get("/api/admin/orders/999999/communications")
    assert resp.status_code == 404


def test_admin_list_communications_requires_admin(client, db_session, test_photos):
    order = _create_ready_order_with_delivery(db_session, test_photos)
    resp = client.get(f"/api/admin/orders/{order.id}/communications")
    assert resp.status_code == 401


def test_admin_send_email_creates_communication_and_queues_task(
    admin_client, db_session, test_photos, mock_celery_send_task
):
    from photostore.models import Communication, CommunicationKind, CommunicationStatus

    order = _create_ready_order_with_delivery(db_session, test_photos)

    resp = admin_client.post(
        f"/api/admin/orders/{order.id}/communications/send",
        json={"kind": "DOWNLOAD_READY"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "DOWNLOAD_READY"
    assert data["status"] == "QUEUED"
    assert data["initiated_by"] == "admin"

    comm = db_session.query(Communication).filter(
        Communication.order_id == order.id,
        Communication.kind == CommunicationKind.DOWNLOAD_READY,
    ).first()
    assert comm is not None
    assert comm.status == CommunicationStatus.QUEUED

    send_email_calls = [
        c for c in mock_celery_send_task.call_args_list
        if c.args and c.args[0] == "tasks.send_email.send_email"
    ]
    assert len(send_email_calls) == 1
    assert send_email_calls[0].kwargs["args"] == [comm.id]


def test_admin_send_email_order_not_found(admin_client):
    resp = admin_client.post(
        "/api/admin/orders/999999/communications/send",
        json={"kind": "ORDER_CONFIRMED"},
    )
    assert resp.status_code == 404


def test_admin_send_email_requires_admin(client, db_session, test_photos):
    order = _create_ready_order_with_delivery(db_session, test_photos)
    resp = client.post(
        f"/api/admin/orders/{order.id}/communications/send",
        json={"kind": "ORDER_CONFIRMED"},
    )
    assert resp.status_code == 401


def test_admin_reset_delivery_queues_delivery_reset_email(
    admin_client, db_session, test_photos, mock_celery_send_task, monkeypatch
):
    """reset-delivery should enqueue a DELIVERY_RESET email when EMAIL_ENABLED=True."""
    from photostore.config import settings
    from photostore.models import Communication, CommunicationKind

    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    order = _create_ready_order_with_delivery(db_session, test_photos)

    resp = admin_client.post(
        f"/api/admin/orders/{order.id}/reset-delivery",
        json={"rotate_token": True, "days_valid": 30},
    )
    assert resp.status_code == 200

    comm = db_session.query(Communication).filter(
        Communication.order_id == order.id,
        Communication.kind == CommunicationKind.DELIVERY_RESET,
    ).first()
    assert comm is not None

    send_email_calls = [
        c for c in mock_celery_send_task.call_args_list
        if c.args and c.args[0] == "tasks.send_email.send_email"
    ]
    assert len(send_email_calls) == 1
