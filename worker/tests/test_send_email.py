"""Tests for the send_email Celery task.

Tasks are invoked via .apply() for synchronous eager execution.
SessionLocal is monkeypatched to return the test's transactional session.
The Brevo HTTP provider is mocked so no real network calls are made.
"""

import importlib
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_se_module():
    if "worker.tasks.send_email" not in sys.modules:
        importlib.import_module("worker.tasks.send_email")
    return sys.modules["worker.tasks.send_email"]


def _get_send_email_task():
    return _get_se_module().send_email


def _seed_order_and_communication(db_session, kind="ORDER_CONFIRMED"):
    from photostore.models import (
        Communication, CommunicationKind, CommunicationStatus,
        Event, Order, OrderStatus,
    )

    event = Event(
        slug="email-test",
        name="Email Test Race",
        date=datetime(2026, 3, 9, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    order = Order(
        stripe_session_id=f"cs_test_email_{kind}",
        email="runner@example.com",
        status=OrderStatus.PAID,
    )
    db_session.add(order)
    db_session.flush()

    comm = Communication(
        order_id=order.id,
        kind=CommunicationKind(kind),
        provider="brevo",
        recipient_email=order.email,
        subject="Test subject",
        template_key=kind,
        status=CommunicationStatus.QUEUED,
        initiated_by="system",
        dedupe_key=f"order:{order.id}:{kind}:v1",
    )
    db_session.add(comm)
    db_session.flush()

    return order, comm


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_send_email_creates_sent_communication_row(db_session, monkeypatch):
    from photostore.models import Communication, CommunicationStatus

    se_module = _get_se_module()

    order, comm = _seed_order_and_communication(db_session)

    mock_provider = MagicMock()
    mock_provider.send.return_value = "msg-brevo-123"

    monkeypatch.setattr(se_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(se_module, "_get_provider", lambda: mock_provider)

    _get_send_email_task().apply(args=[comm.id])

    db_session.refresh(comm)
    assert comm.status == CommunicationStatus.SENT
    assert comm.provider_message_id == "msg-brevo-123"
    assert comm.sent_at is not None
    assert comm.body_html is not None
    assert comm.body_text is not None


def test_send_email_stores_rendered_bodies(db_session, monkeypatch):
    se_module = _get_se_module()
    order, comm = _seed_order_and_communication(db_session)

    mock_provider = MagicMock()
    mock_provider.send.return_value = "msg-brevo-456"

    monkeypatch.setattr(se_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(se_module, "_get_provider", lambda: mock_provider)

    _get_send_email_task().apply(args=[comm.id])

    db_session.refresh(comm)
    assert "<html" in comm.body_html.lower() or len(comm.body_html) > 10
    assert len(comm.body_text) > 10


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def test_send_email_provider_failure_sets_failed(db_session, monkeypatch):
    from photostore.models import CommunicationStatus

    se_module = _get_se_module()
    order, comm = _seed_order_and_communication(db_session, kind="DOWNLOAD_READY")

    mock_provider = MagicMock()
    mock_provider.send.side_effect = Exception("Brevo returned 500")

    monkeypatch.setattr(se_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(se_module, "_get_provider", lambda: mock_provider)

    # apply() with throw=False so we can inspect the result without raising
    result = _get_send_email_task().apply(args=[comm.id], throw=False)

    db_session.refresh(comm)
    assert comm.status == CommunicationStatus.FAILED
    assert "Brevo returned 500" in comm.error_message


def test_send_email_retry_updates_existing_row_not_creates_new(db_session, monkeypatch):
    """Retries must update the existing communication row, not insert a new one."""
    from photostore.models import Communication, CommunicationStatus

    se_module = _get_se_module()
    order, comm = _seed_order_and_communication(db_session)

    call_count = {"n": 0}

    def _flaky_send(msg):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise Exception("transient failure")
        return "msg-retry-success"

    mock_provider = MagicMock()
    mock_provider.send.side_effect = _flaky_send

    monkeypatch.setattr(se_module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(se_module, "_get_provider", lambda: mock_provider)

    # Patch retry to call task again immediately (no real Celery broker)
    original_task = _get_send_email_task()

    with patch.object(original_task, "retry", side_effect=lambda exc, countdown: original_task.apply(args=[comm.id]).get()):
        _get_send_email_task().apply(args=[comm.id])

    total_comm_rows = db_session.query(Communication).filter(
        Communication.order_id == order.id
    ).count()
    assert total_comm_rows == 1


def test_send_email_missing_communication_row_raises(db_session, monkeypatch):
    se_module = _get_se_module()

    monkeypatch.setattr(se_module, "SessionLocal", lambda: db_session)

    result = _get_send_email_task().apply(args=[999999], throw=False)
    assert result.failed()
