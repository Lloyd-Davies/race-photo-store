"""Tests for the build_zip Celery task.

Tasks are invoked via .apply() for synchronous eager execution.
SessionLocal is monkeypatched to return the test's transactional session.
"""

import importlib
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from photostore.models import (
    Delivery, Event, Order, OrderItem, OrderStatus, Photo,
)


def _get_bz_module():
    """Return the worker.tasks.build_zip module, bypassing __init__ re-exports."""
    if "worker.tasks.build_zip" not in sys.modules:
        importlib.import_module("worker.tasks.build_zip")
    return sys.modules["worker.tasks.build_zip"]


def _get_build_zip_task():
    return _get_bz_module().build_zip


def _seed(db_session, storage: Path, with_originals=True):
    """Create event, 3 photos, and a PAID order. Returns the Order."""
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
            original.write_bytes(b"FAKEJPEG_ORIGINAL")

        db_session.add(Photo(
            id=pid,
            event_id=event.id,
            proof_path=f"proofs/{event.slug}/{pid}.jpg",
            original_path=f"originals/{event.slug}/{pid}.jpg",
        ))

    order = Order(
        stripe_session_id=f"cs_test_build_zip_{with_originals}",
        email="runner@example.com",
        status=OrderStatus.PAID,
    )
    db_session.add(order)
    db_session.flush()

    for pid in photo_ids:
        db_session.add(OrderItem(
            order_id=order.id,
            photo_id=pid,
            unit_price_pence=500,
        ))

    db_session.flush()
    return order


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_build_zip_creates_zip_file(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    bz_module = _get_bz_module()

    storage = tmp_path / "photos"
    order = _seed(db_session, storage)

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    _get_build_zip_task().apply(args=[order.id])

    zip_path = storage / "zips" / f"order-{order.id}.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        assert len(zf.namelist()) == 3


def test_build_zip_sets_readable_permissions(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    bz_module = _get_bz_module()

    storage = tmp_path / "photos"
    order = _seed(db_session, storage)

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    _get_build_zip_task().apply(args=[order.id])

    zip_path = storage / "zips" / f"order-{order.id}.zip"
    mode = os.stat(zip_path).st_mode
    assert mode & 0o004


def test_build_zip_marks_order_ready(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    bz_module = _get_bz_module()

    storage = tmp_path / "photos"
    order = _seed(db_session, storage)

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    _get_build_zip_task().apply(args=[order.id])

    db_session.refresh(order)
    assert order.status == OrderStatus.READY


def test_build_zip_creates_delivery_token(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    bz_module = _get_bz_module()

    storage = tmp_path / "photos"
    order = _seed(db_session, storage)

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    _get_build_zip_task().apply(args=[order.id])

    delivery = db_session.query(Delivery).filter(Delivery.order_id == order.id).first()
    assert delivery is not None
    assert len(delivery.token) == 36  # UUID format
    assert delivery.download_count == 0
    assert delivery.max_downloads == 5


# ---------------------------------------------------------------------------
# Error path — missing originals
# ---------------------------------------------------------------------------

def test_build_zip_marks_order_failed_on_missing_original(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    bz_module = _get_bz_module()

    storage = tmp_path / "photos"
    order = _seed(db_session, storage, with_originals=False)

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    result = _get_build_zip_task().apply(args=[order.id])
    assert result.failed()

    db_session.refresh(order)
    assert order.status == OrderStatus.FAILED


# ---------------------------------------------------------------------------
# Email trigger
# ---------------------------------------------------------------------------

def test_build_zip_queues_download_ready_email(db_session, tmp_path, monkeypatch):
    """build_zip should enqueue a DOWNLOAD_READY send_email task after READY."""
    from unittest.mock import patch

    from photostore.config import settings
    from photostore.models import Communication, CommunicationKind

    bz_module = _get_bz_module()

    storage = tmp_path / "photos"
    order = _seed(db_session, storage)

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(bz_module, "SessionLocal", lambda: db_session)

    with patch.object(bz_module.celery_app, "send_task") as mock_send:
        _get_build_zip_task().apply(args=[order.id])

    comm = (
        db_session.query(Communication)
        .filter(Communication.order_id == order.id)
        .filter(Communication.kind == CommunicationKind.DOWNLOAD_READY)
        .first()
    )
    assert comm is not None, "Communication row was not created"

    email_calls = [c for c in mock_send.call_args_list if "send_email" in str(c)]
    assert len(email_calls) == 1
    assert email_calls[0].kwargs["args"] == [comm.id]
