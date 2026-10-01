from datetime import timedelta
from unittest.mock import MagicMock
import importlib
import pytest
from photostore.models import CommunicationStatus, DeliveryZipStatus, Order, OrderStatus, RecoveryActivation, RecoveryJob
from photostore.recovery import ensure_job, now, task_lock
from .test_send_email import _seed_order_and_communication, _get_se_module
from .test_build_zip import _seed, _get_bz_module, _configure_paths


def module():
    return importlib.import_module("worker.tasks.recover_orders")


def seed(db):
    order = Order(stripe_session_id="cs_recovery", email="runner@example.com", status=OrderStatus.PENDING,
                  created_at=now()-timedelta(minutes=20))
    db.add(order)
    db.flush()
    db.get(RecoveryActivation, 1).activated_at = now()-timedelta(days=1)
    db.flush()
    return order


def test_missed_webhook_recovers_without_customer_polling(db_session, monkeypatch):
    from photostore.config import settings
    m = module()
    order = seed(db_session)
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_synthetic")
    monkeypatch.setattr(m.stripe.checkout.Session, "retrieve", lambda *a, **kw: {"id": order.stripe_session_id, "payment_status": "paid"})
    assert m.recover_orders.run() == 1
    assert order.status == OrderStatus.READY
    assert db_session.query(RecoveryJob).filter_by(kind="payment").one().status == "DONE"


def test_dispatch_failure_is_sanitized_and_retried(db_session, monkeypatch):
    from photostore.config import settings
    m = module()
    order, comm = _seed_order_and_communication(db_session)
    job = ensure_job(db_session, order.id, "email", comm.id, approved=True)
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    dispatch = MagicMock(side_effect=ConnectionError("credentials should never appear"))
    monkeypatch.setattr(m.celery_app, "send_task", dispatch)
    m.recover_orders.run()
    assert job.status == "PENDING" and job.attempts == 1
    assert job.error == "ConnectionError"
    assert job.next_attempt_at > now()
    dispatch.side_effect = None
    job.next_attempt_at = now()-timedelta(seconds=1)
    db_session.flush()
    m.recover_orders.run()
    assert dispatch.call_count == 2


def test_twenty_four_hour_window_requires_review(db_session, monkeypatch):
    from photostore.config import settings
    m = module()
    order = seed(db_session)
    job = ensure_job(db_session, order.id, "payment", order.id)
    job.created_at = now()-timedelta(hours=25)
    db_session.flush()
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    retrieve = MagicMock()
    monkeypatch.setattr(m.stripe.checkout.Session, "retrieve", retrieve)
    m.recover_orders.run()
    assert job.status == "REVIEW"
    retrieve.assert_not_called()


def test_historical_payment_is_not_automatically_selected(db_session, monkeypatch):
    from photostore.config import settings
    m = module()
    order = seed(db_session)
    order.created_at = now()-timedelta(days=2)
    db_session.flush()
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    assert m.recover_orders.run() == 0
    assert db_session.query(RecoveryJob).count() == 0


def test_duplicate_email_task_does_not_resend(db_session, monkeypatch):
    from photostore.config import settings
    m = _get_se_module()
    _, comm = _seed_order_and_communication(db_session)
    provider = MagicMock()
    provider.send.return_value = "message-id"
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(m, "_get_provider", lambda: provider)
    m.send_email.run(comm.id)
    m.send_email.run(comm.id)
    provider.send.assert_called_once()
    assert comm.status == CommunicationStatus.SENT


def test_concurrent_email_task_is_skipped(db_session, monkeypatch):
    from photostore.config import settings
    m = _get_se_module()
    _, comm = _seed_order_and_communication(db_session)
    provider = MagicMock()
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(m, "_get_provider", lambda: provider)
    with task_lock(db_session, 7211, comm.id):
        m.send_email.run(comm.id)
    provider.send.assert_not_called()


def test_duplicate_zip_build_does_not_upload_twice(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    m = _get_bz_module()
    order, delivery = _seed(db_session, tmp_path)
    _configure_paths(monkeypatch, settings, tmp_path)
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    m.build_zip.run(order.id)
    before = delivery.zip_created_at
    m.build_zip.run(order.id)
    assert delivery.zip_created_at == before
    assert delivery.zip_status == DeliveryZipStatus.READY


def test_interrupted_requested_zip_is_requeued(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    m = module()
    order, delivery = _seed(db_session, tmp_path)
    delivery.zip_status = DeliveryZipStatus.BUILDING
    ensure_job(db_session, order.id, "zip", order.id, approved=True)
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    dispatch = MagicMock()
    monkeypatch.setattr(m.celery_app, "send_task", dispatch)
    m.recover_orders.run()
    dispatch.assert_called_once_with("tasks.build_zip.build_zip", args=[order.id])


def test_no_zip_created_without_customer_request(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    m = module()
    _seed(db_session, tmp_path)
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    dispatch = MagicMock()
    monkeypatch.setattr(m.celery_app, "send_task", dispatch)
    m.recover_orders.run()
    dispatch.assert_not_called()


def test_database_failure_does_not_contact_providers(monkeypatch):
    from photostore.config import settings
    m = module()
    monkeypatch.setattr(m, "SessionLocal", MagicMock(side_effect=ConnectionError("offline")))
    dispatch = MagicMock()
    monkeypatch.setattr(m.celery_app, "send_task", dispatch)
    with pytest.raises(ConnectionError):
        m.recover_orders.run()
    dispatch.assert_not_called()


def test_brevo_deduplicates_with_stable_uuid(monkeypatch):
    from photostore.config import settings
    import httpx
    from photostore.email_provider import BrevoProvider, EmailMessage
    request = MagicMock(return_value=httpx.Response(400, json={"code": "duplicate_parameter", "message": "Email for this idempotency key has already been processed"}))
    monkeypatch.setattr(httpx, "post", request)
    msg = EmailMessage("runner@example.com", "Runner", "Photos", "html", "text", "sender@example.com", "Store", "a1b2c3d4-e5f6-4a1b-8c2d-3e4f5a6b7c8d")
    assert BrevoProvider("synthetic").send(msg) == "deduplicated"
    assert request.call_args.kwargs["json"]["headers"]["idempotencyKey"] == msg.idempotency_key


def test_uncertain_accepted_email_is_retried_with_same_body_and_key(db_session, monkeypatch):
    m = _get_se_module()
    _, comm = _seed_order_and_communication(db_session)
    provider = MagicMock()
    provider.send.return_value = "accepted-message"
    monkeypatch.setattr(m, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(m, "_get_provider", lambda: provider)
    commits = 0
    def commit():
        nonlocal commits
        commits += 1
        if commits == 2:
            raise ConnectionError("lost response after acceptance")
        db_session.flush()
    class FaultSession:
        def __getattr__(self, name):
            return getattr(db_session, name)
        def commit(self):
            commit()
    monkeypatch.setattr(m, "SessionLocal", FaultSession)
    with pytest.raises(ConnectionError):
        m.send_email.run(comm.id)
    assert comm.status == CommunicationStatus.FAILED
    m.send_email.run(comm.id)
    first, second = [c.args[0] for c in provider.send.call_args_list]
    assert first.idempotency_key == second.idempotency_key
    assert first.html_body == second.html_body
    assert comm.status == CommunicationStatus.SENT


def test_other_duplicate_parameter_errors_do_not_mark_sent(monkeypatch):
    import httpx
    from photostore.email_provider import BrevoProvider, EmailMessage, ProviderError
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(400, json={"code": "duplicate_parameter", "message": "Duplicate unrelated parameter"}))
    with pytest.raises(ProviderError):
        BrevoProvider("synthetic").send(EmailMessage("runner@example.com", "Runner", "Photos", "html", "text", "sender@example.com", "Store", "a1b2c3d4-e5f6-4a1b-8c2d-3e4f5a6b7c8d"))
