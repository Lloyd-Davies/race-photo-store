"""Tests for ZIP lifecycle Celery tasks."""

import importlib
import io
import os
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from photostore.models import (
    Delivery,
    DeliveryZipStatus,
    Event,
    Order,
    OrderItem,
    OrderStatus,
    Photo,
)


def _get_bz_module():
    if "worker.tasks.build_zip" not in sys.modules:
        importlib.import_module("worker.tasks.build_zip")
    return sys.modules["worker.tasks.build_zip"]


def _get_cleanup_module():
    if "worker.tasks.cleanup_expired_zips" not in sys.modules:
        importlib.import_module("worker.tasks.cleanup_expired_zips")
    return sys.modules["worker.tasks.cleanup_expired_zips"]


def _get_build_zip_task():
    return _get_bz_module().build_zip


def _get_cleanup_task():
    return _get_cleanup_module().cleanup_expired_zips


def _seed(db_session, storage: Path, with_originals=True):
    event = Event(
        slug="zip-test",
        name="Zip Test Race",
        date=datetime(2026, 2, 18, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    photo_ids = [f"zip-photo-{i}" for i in range(1, 4)]
    for pid in photo_ids:
        proof = storage / "proofs" / event.slug / f"{pid}.jpg"
        proof.parent.mkdir(parents=True, exist_ok=True)
        proof.write_bytes(b"FAKEJPEG_PROOF")

        if with_originals:
            original = storage / "originals" / event.slug / f"{pid}.jpg"
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(f"ORIGINAL_{pid}".encode("ascii"))

        db_session.add(
            Photo(
                id=pid,
                event_id=event.id,
                proof_path=f"proofs/{event.slug}/{pid}.jpg",
                original_path=f"originals/{event.slug}/{pid}.jpg",
            )
        )

    order = Order(
        stripe_session_id=f"cs_test_build_zip_{with_originals}",
        email="runner@example.com",
        status=OrderStatus.READY,
    )
    db_session.add(order)
    db_session.flush()

    for pid in photo_ids:
        db_session.add(OrderItem(order_id=order.id, photo_id=pid, unit_price_pence=500))

    delivery = Delivery(
        order_id=order.id,
        token="zip-token",
        zip_path=None,
        event_slug=event.slug,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        max_downloads=100,
        download_count=0,
        zip_status=DeliveryZipStatus.NOT_REQUESTED,
    )
    db_session.add(delivery)
    db_session.flush()
    return order, delivery


def _configure_paths(monkeypatch, settings, storage: Path):
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(settings, "CACHE_ROOT", str(storage / "cache"))
    monkeypatch.setattr(settings, "ZIP_TTL_DAYS", 3)


def test_build_zip_creates_zip_file_and_marks_delivery_ready(db_session, tmp_path, monkeypatch):
    from photostore.config import settings

    bz_module = _get_bz_module()
    storage = tmp_path / "photos"
    order, delivery = _seed(db_session, storage)

    _configure_paths(monkeypatch, settings, storage)
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    _get_build_zip_task().apply(args=[order.id])

    zip_path = storage / "zips" / f"order-{order.id}.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.namelist() == ["zip-photo-1.jpg", "zip-photo-2.jpg", "zip-photo-3.jpg"]

    db_session.refresh(delivery)
    db_session.refresh(order)
    assert delivery.token == "zip-token"
    assert delivery.zip_path == f"zips/order-{order.id}.zip"
    assert delivery.zip_status == DeliveryZipStatus.READY
    assert delivery.zip_created_at is not None
    assert delivery.zip_expires_at is not None
    assert delivery.zip_error is None
    assert order.status == OrderStatus.READY


def test_build_zip_sets_readable_permissions(db_session, tmp_path, monkeypatch):
    from photostore.config import settings

    bz_module = _get_bz_module()
    storage = tmp_path / "photos"
    order, _ = _seed(db_session, storage)

    _configure_paths(monkeypatch, settings, storage)
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    _get_build_zip_task().apply(args=[order.id])

    zip_path = storage / "zips" / f"order-{order.id}.zip"
    mode = os.stat(zip_path).st_mode
    assert mode & 0o004


def test_build_zip_uploads_zip_to_configured_backend(
    db_session,
    tmp_path,
    monkeypatch,
):
    from photostore.config import settings

    class FakeZipStorage:
        def __init__(self):
            self.uploads = []

        def upload_file(self, source, key, content_type=None):
            self.uploads.append(
                {
                    "key": key,
                    "content_type": content_type,
                    "content": Path(source).read_bytes(),
                }
            )

    bz_module = _get_bz_module()
    storage = tmp_path / "photos"
    order, delivery = _seed(db_session, storage)
    zip_storage = FakeZipStorage()

    _configure_paths(monkeypatch, settings, storage)
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(bz_module, "get_storage_backend", lambda: zip_storage)

    _get_build_zip_task().apply(args=[order.id])

    assert len(zip_storage.uploads) == 1
    upload = zip_storage.uploads[0]
    assert upload["key"] == f"zips/order-{order.id}.zip"
    assert upload["content_type"] == "application/zip"
    assert not (storage / "zips" / f"order-{order.id}.zip").exists()
    with zipfile.ZipFile(io.BytesIO(upload["content"])) as zf:
        assert zf.namelist() == ["zip-photo-1.jpg", "zip-photo-2.jpg", "zip-photo-3.jpg"]

    db_session.refresh(delivery)
    assert delivery.zip_status == DeliveryZipStatus.READY
    assert delivery.zip_path == f"zips/order-{order.id}.zip"


def test_build_zip_regenerates_existing_zip(db_session, tmp_path, monkeypatch):
    from photostore.config import settings

    bz_module = _get_bz_module()
    storage = tmp_path / "photos"
    order, delivery = _seed(db_session, storage)
    existing = storage / "zips" / f"order-{order.id}.zip"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"OLD")
    delivery.zip_path = f"zips/order-{order.id}.zip"
    delivery.zip_status = DeliveryZipStatus.EXPIRED
    db_session.flush()

    _configure_paths(monkeypatch, settings, storage)
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    _get_build_zip_task().apply(args=[order.id])

    with zipfile.ZipFile(existing) as zf:
        assert len(zf.namelist()) == 3
    db_session.refresh(delivery)
    assert delivery.zip_status == DeliveryZipStatus.READY
    assert delivery.zip_deleted_at is None


def test_build_zip_marks_delivery_failed_without_failing_order(
    db_session,
    tmp_path,
    monkeypatch,
):
    from photostore.config import settings

    bz_module = _get_bz_module()
    storage = tmp_path / "photos"
    order, delivery = _seed(db_session, storage, with_originals=False)

    _configure_paths(monkeypatch, settings, storage)
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    result = _get_build_zip_task().apply(args=[order.id], throw=False)

    assert result.failed()
    db_session.refresh(order)
    db_session.refresh(delivery)
    assert order.status == OrderStatus.READY
    assert delivery.zip_status == DeliveryZipStatus.FAILED
    assert "Original not found" in delivery.zip_error


def test_build_zip_requires_existing_delivery(db_session, tmp_path, monkeypatch):
    from photostore.config import settings

    bz_module = _get_bz_module()
    storage = tmp_path / "photos"
    order, delivery = _seed(db_session, storage)
    db_session.delete(delivery)
    db_session.flush()

    _configure_paths(monkeypatch, settings, storage)
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    result = _get_build_zip_task().apply(args=[order.id], throw=False)

    assert result.failed()


def test_cleanup_expired_zips_deletes_artifact_and_preserves_order(
    db_session,
    tmp_path,
    monkeypatch,
):
    from photostore.config import settings

    cleanup_module = _get_cleanup_module()
    storage = tmp_path / "photos"
    order, delivery = _seed(db_session, storage)
    zip_path = storage / "zips" / f"order-{order.id}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(b"PK")
    delivery.zip_path = f"zips/order-{order.id}.zip"
    delivery.zip_status = DeliveryZipStatus.READY
    delivery.zip_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()

    _configure_paths(monkeypatch, settings, storage)
    monkeypatch.setattr(settings, "ZIP_CLEANUP_ENABLED", True)
    monkeypatch.setattr(cleanup_module, "SessionLocal", lambda: db_session)

    result = _get_cleanup_task().apply().get()

    assert result == 1
    assert not zip_path.exists()
    db_session.refresh(order)
    db_session.refresh(delivery)
    assert order.status == OrderStatus.READY
    assert delivery.zip_status == DeliveryZipStatus.EXPIRED
    assert delivery.zip_deleted_at is not None


def test_cleanup_expired_zips_deletes_via_storage_backend(
    db_session,
    tmp_path,
    monkeypatch,
):
    from photostore.config import settings

    class FakeZipStorage:
        def __init__(self):
            self.deleted = []

        def delete(self, key):
            self.deleted.append(key)

    cleanup_module = _get_cleanup_module()
    storage = tmp_path / "photos"
    order, delivery = _seed(db_session, storage)
    delivery.zip_path = f"zips/order-{order.id}.zip"
    delivery.zip_status = DeliveryZipStatus.READY
    delivery.zip_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()
    zip_storage = FakeZipStorage()

    _configure_paths(monkeypatch, settings, storage)
    monkeypatch.setattr(settings, "ZIP_CLEANUP_ENABLED", True)
    monkeypatch.setattr(cleanup_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(cleanup_module, "get_storage_backend", lambda: zip_storage)

    result = _get_cleanup_task().apply().get()

    assert result == 1
    assert zip_storage.deleted == [f"zips/order-{order.id}.zip"]
    db_session.refresh(order)
    db_session.refresh(delivery)
    assert order.status == OrderStatus.READY
    assert delivery.zip_status == DeliveryZipStatus.EXPIRED
    assert delivery.zip_deleted_at is not None
