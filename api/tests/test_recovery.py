from datetime import timedelta
from unittest.mock import patch
import pytest
from photostore.models import Communication, Delivery, DeliveryZipStatus, Event, Photo, OrderItem, Order, OrderStatus, RecoveryActivation, RecoveryJob
from photostore.recovery import ensure_job, now, task_lock
from .test_orders import _order_access


def seed(db, status=OrderStatus.PENDING):
    event = Event(slug="recovery-fixture", name="Synthetic recovery", date=now())
    db.add(event)
    db.flush()
    photo = Photo(id="recovery-photo", event_id=event.id, proof_path="proofs/synthetic.jpg", original_path="originals/synthetic.jpg")
    db.add(photo)
    order = Order(stripe_session_id="cs_recovery", email="runner@example.com", status=status)
    db.add(order)
    db.flush()
    db.add(OrderItem(order_id=order.id, photo_id=photo.id, unit_price_pence=500))
    db.flush()
    return order


@pytest.mark.parametrize("session", [
    {"payment_status": "unpaid", "status": "complete"},
    {"status": "complete"},
    {"payment_status": "no_payment_required", "status": "complete", "amount_total": 500},
])
def test_all_entrypoints_reject_unconfirmed_payment(db_session, session):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    from app.routes.admin import _apply_stripe_session_to_order
    from app.routes.webhook import _handle_checkout_completed
    order = seed(db_session)
    session["id"] = order.stripe_session_id
    assert not _apply_stripe_session_to_order(order, session, db_session, actor="admin")[0]
    assert _handle_checkout_completed(session, db_session)[0] is None
    assert order.status == OrderStatus.PENDING
    assert db_session.query(Delivery).count() == 0


def test_confirmed_free_stripe_checkout_is_supported(db_session):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    order = seed(db_session)
    confirmed, _ = confirm_payment(order, {"id": order.stripe_session_id,
        "payment_status": "no_payment_required", "status": "complete", "amount_total": 0}, db_session)
    assert confirmed and order.status == OrderStatus.READY


def test_duplicate_confirmation_preserves_delivery_and_email(db_session, monkeypatch):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    order = seed(db_session)
    session = {"id": order.stripe_session_id, "payment_status": "paid"}
    confirm_payment(order, session, db_session)
    db_session.flush()
    delivery = db_session.query(Delivery).one()
    delivery.download_count = 2
    before = (delivery.token, delivery.expires_at, delivery.max_downloads)
    confirm_payment(order, session, db_session)
    db_session.flush()
    assert db_session.query(Delivery).count() == 1
    assert db_session.query(Communication).count() == 1
    assert db_session.query(RecoveryJob).filter_by(kind="email").count() == 1
    assert (delivery.token, delivery.expires_at, delivery.max_downloads) == before
    assert delivery.download_count == 2


@pytest.mark.parametrize("reason", ["refund", "expired", "exhausted"])
def test_recovery_selection_rejects_excluded_orders(admin_client, db_session, reason):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    order = seed(db_session)
    if reason == "refund":
        order.stripe_amount_refunded_pence = 1
    elif reason == "expired":
        order.status = OrderStatus.EXPIRED
    else:
        db_session.add(Delivery(order_id=order.id, token="exhausted", event_slug="test",
            expires_at=now()+timedelta(days=1), max_downloads=1, download_count=1))
    db_session.flush()
    response = admin_client.post(f"/api/admin/orders/{order.id}/recovery")
    assert response.status_code == 409
    assert db_session.query(RecoveryJob).count() == 0


def test_historical_preview_does_not_mutate_and_selection_is_explicit(admin_client, db_session):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    order = seed(db_session)
    order.created_at = db_session.get(RecoveryActivation, 1).activated_at - timedelta(days=1)
    db_session.flush()
    assert ensure_job(db_session, order.id, "payment", order.id) is None
    preview = admin_client.get("/api/admin/recovery/preview").json()
    assert preview["candidates"][0]["order_id"] == order.id
    assert db_session.query(RecoveryJob).count() == 0
    assert admin_client.post(f"/api/admin/orders/{order.id}/recovery").status_code == 200
    assert db_session.query(RecoveryJob).count() == 1


def test_recovery_endpoints_require_admin(client, db_session):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    order = seed(db_session)
    assert client.get("/api/admin/recovery/preview").status_code == 401
    assert client.post(f"/api/admin/orders/{order.id}/recovery").status_code == 401


def test_zip_broker_failure_keeps_durable_requested_job(client, db_session):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    order = seed(db_session, OrderStatus.READY)
    with patch("app.routes.orders.celery_app.send_task", side_effect=ConnectionError("secret")):
        response = client.post(f"/api/orders/{order.id}/zip", headers={"X-Order-Access": _order_access(order.id)})
    assert response.status_code == 200
    assert response.json()["status"] == "BUILDING"
    assert db_session.query(RecoveryJob).filter_by(kind="zip").one().status == "PENDING"


def test_outbox_rolls_back_with_fulfillment(db_session, monkeypatch):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    order = seed(db_session)
    nested = db_session.begin_nested()
    confirm_payment(order, {"id": order.stripe_session_id, "payment_status": "paid"}, db_session)
    nested.rollback()
    assert db_session.query(RecoveryJob).count() == 0
    assert db_session.query(Delivery).count() == 0


def test_advisory_lock_survives_commit_and_releases(db_session):
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    with task_lock(db_session, 7299, 1) as acquired:
        assert acquired
        db_session.commit()
        with task_lock(db_session, 7299, 1) as duplicate:
            assert not duplicate
    with task_lock(db_session, 7299, 1) as reacquired:
        assert reacquired


def test_concurrent_confirmation_creates_one_grant(db_engine, monkeypatch):
    """Two real PostgreSQL transactions read the same pending order before locking."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4
    from sqlalchemy.orm import Session
    from photostore.config import settings
    from photostore.fulfillment import confirm_payment
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    session_id = f"cs_concurrent_{uuid4()}"
    with Session(db_engine) as db:
        event = Event(slug=f"concurrent-{uuid4()}", name="Synthetic concurrent recovery", date=now())
        db.add(event)
        db.flush()
        photo = Photo(id=f"concurrent-{uuid4()}", event_id=event.id, proof_path="proofs/synthetic.jpg", original_path="originals/synthetic.jpg")
        db.add(photo)
        order = Order(stripe_session_id=session_id, email="runner@example.com", status=OrderStatus.PENDING)
        db.add(order)
        db.flush()
        db.add(OrderItem(order_id=order.id, photo_id=photo.id, unit_price_pence=500))
        db.commit()
        order_id, photo_id, event_id = order.id, photo.id, event.id
    barrier = Barrier(2)
    def confirm():
        with Session(db_engine) as db:
            order = db.get(Order, order_id)
            barrier.wait(timeout=10)
            confirm_payment(order, {"id": session_id, "payment_status": "paid"}, db)
            db.commit()


    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(confirm) for _ in range(2)]
            for future in futures:
                future.result(timeout=20)
        with Session(db_engine) as db:
            assert db.query(Delivery).filter_by(order_id=order_id).count() == 1
            assert db.query(Communication).filter_by(order_id=order_id).count() == 1
            assert db.query(RecoveryJob).filter_by(order_id=order_id).count() == 1
    finally:
        with Session(db_engine) as db:
            for model in (RecoveryJob, Communication, Delivery, OrderItem):
                db.query(model).filter_by(order_id=order_id).delete()
            db.query(Order).filter_by(id=order_id).delete()
            db.query(Photo).filter_by(id=photo_id).delete()
            db.query(Event).filter_by(id=event_id).delete()
            db.commit()


def test_recovery_migration_preserves_existing_order_schema(db_engine, tmp_path):
    """Rehearse schema changes solely on the disposable test cluster."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from uuid import uuid4
    from shutil import copytree, ignore_patterns
    from alembic.util import CommandError
    cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    old_scripts = tmp_path / "prior-alembic"
    copytree(Path(__file__).parents[1] / "alembic", old_scripts,
             ignore=ignore_patterns("0012_order_recovery.py", "__pycache__"))
    old_cfg = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    old_cfg.set_main_option("script_location", str(old_scripts))
    with pytest.raises(CommandError, match="0012"):
        command.upgrade(old_cfg, "head")  # Old images cannot start against an unknown revision.
    with db_engine.begin() as connection:
        order_id = connection.execute(text("INSERT INTO orders (stripe_session_id, email, status, currency, created_at) VALUES (:session, '', 'PENDING', 'GBP', CURRENT_TIMESTAMP) RETURNING id"), {"session": f"cs_schema_{uuid4()}"}).scalar()
        before = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='orders' ORDER BY ordinal_position")).scalars().all()
    try:
        command.downgrade(cfg, "0011")
        with db_engine.connect() as connection:
            assert connection.execute(text("SELECT status FROM orders WHERE id=:id"), {"id": order_id}).scalar() == "PENDING"
        command.upgrade(cfg, "head")
        with db_engine.connect() as connection:
            after = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='orders' ORDER BY ordinal_position")).scalars().all()
            assert before == after
            assert connection.execute(text("SELECT activated_at > created_at FROM orders CROSS JOIN recovery_activation WHERE orders.id=:id"), {"id": order_id}).scalar()
    finally:
        command.upgrade(cfg, "head")
        with db_engine.begin() as connection:
            connection.execute(text("DELETE FROM orders WHERE id=:id"), {"id": order_id})


def test_worker_crash_releases_external_side_effect_lock(db_engine):
    import os
    import subprocess
    import sys
    import time
    from sqlalchemy.orm import Session
    environment = dict(os.environ, SYNTHETIC_DATABASE_URL=db_engine.url.render_as_string(hide_password=False))
    code = "import os,sys; from sqlalchemy import create_engine,text; c=create_engine(os.environ['SYNTHETIC_DATABASE_URL']).connect(); c.execute(text('SELECT pg_advisory_lock(7299,2)')); print('locked',flush=True); sys.stdin.read()"
    process = subprocess.Popen([sys.executable, "-c", code], env=environment,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "locked"
        with Session(db_engine) as db, task_lock(db, 7299, 2) as acquired:
            assert not acquired
        process.kill()
        process.wait(timeout=10)
        for _ in range(20):
            with Session(db_engine) as db, task_lock(db, 7299, 2) as acquired:
                if acquired:
                    return
            time.sleep(0.05)
        pytest.fail("PostgreSQL did not release the crashed worker lock")
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)
