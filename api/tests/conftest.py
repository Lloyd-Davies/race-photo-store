"""
Pytest fixtures for the PhotoStore API test suite.

Database strategy:
- A Postgres container is started once per session (testcontainers).
- Alembic migrations run once against it.
- Each test gets its own transaction that is rolled back on teardown,
  so tests are isolated and the schema is never recreated between tests.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from testcontainers.postgres import PostgresContainer

# ── Must set env vars BEFORE importing anything that reads pydantic settings ─
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("STORAGE_ROOT", "/tmp/photostore-test")
os.environ.setdefault("STRIPE_SECRET_KEY", "")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "")
os.environ.setdefault("STRIPE_PRICE_ID", "")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")


# ── Session-scoped Postgres container ────────────────────────────────────────

@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_engine(pg_container):
    """Create engine, run migrations once for the whole test session."""
    url = pg_container.get_connection_url().replace("psycopg2", "psycopg")
    os.environ["DATABASE_URL"] = url

    from alembic.config import Config
    from alembic import command

    engine = create_engine(url, pool_pre_ping=True)

    api_dir = Path(__file__).parent.parent
    alembic_cfg = Config(str(api_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(api_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()


# ── Per-test transactional isolation ─────────────────────────────────────────

@pytest.fixture()
def db_session(db_engine):
    """
    Each test runs in a transaction that is rolled back afterwards.
    This keeps tests isolated without recreating the schema each time.
    """
    connection = db_engine.connect()
    transaction = connection.begin()

    TestSession = sessionmaker(bind=connection)
    session = TestSession()

    # Propagate savepoints so nested commits don't permanently write data
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    session.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ── TestClient with overridden DB dependency ──────────────────────────────────

@pytest.fixture()
def client(db_session):
    from app.main import app
    from app.deps import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Admin client helper ───────────────────────────────────────────────────────

@pytest.fixture()
def admin_client(client):
    """TestClient with admin token pre-set."""
    client.headers.update({"X-Admin-Token": "test-admin-token"})
    return client


# ── Common data fixtures ──────────────────────────────────────────────────────

@pytest.fixture()
def test_event(db_session):
    """A persisted Event row ready for use in tests."""
    from photostore.models import Event
    from datetime import datetime, timezone

    evt = Event(
        slug="test-event",
        name="Test Race 2026",
        date=datetime(2026, 2, 18, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(evt)
    db_session.flush()
    return evt


@pytest.fixture()
def test_photos(db_session, test_event, tmp_path, monkeypatch):
    """
    Three Photo rows with actual proof + original files on disk
    so ingest and build_zip tests have real files to work with.
    Returns a tuple of (photos_list, storage_root_path).
    """
    from photostore.config import settings
    from photostore.models import Photo

    storage = tmp_path / "photos"
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))

    photos = []
    for i in range(1, 4):
        pid = f"photo-{i:03d}"
        proof = storage / "proofs" / test_event.slug / f"{pid}.jpg"
        original = storage / "originals" / test_event.slug / f"{pid}.jpg"
        proof.parent.mkdir(parents=True, exist_ok=True)
        original.parent.mkdir(parents=True, exist_ok=True)
        proof.write_bytes(b"FAKEJPEG")
        original.write_bytes(b"FAKEJPEG")

        p = Photo(
            id=pid,
            event_id=test_event.id,
            proof_path=f"proofs/{test_event.slug}/{pid}.jpg",
            original_path=f"originals/{test_event.slug}/{pid}.jpg",
        )
        db_session.add(p)
        photos.append(p)

    db_session.flush()
    return photos


@pytest.fixture()
def test_cart(db_session, test_event, test_photos):
    """A Cart containing all three test photos."""
    import uuid
    from datetime import datetime, timedelta, timezone
    from photostore.models import Cart

    cart = Cart(
        id=uuid.uuid4(),
        event_id=test_event.id,
        email="runner@example.com",
        items_json=[p.id for p in test_photos],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(cart)
    db_session.flush()
    return cart


# ── Stripe mock ───────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_stripe(test_cart):
    """Patches stripe.Price.retrieve and stripe.checkout.Session.create."""
    fake_session = MagicMock()
    fake_session.id = "cs_test_fakesessionid"
    fake_session.url = "https://checkout.stripe.com/test"

    fake_price = MagicMock()
    fake_price.unit_amount = 500  # £5.00

    with (
        patch("stripe.Price.retrieve", return_value=fake_price),
        patch("stripe.checkout.Session.create", return_value=fake_session),
        patch("stripe.Webhook.construct_event") as mock_construct,
    ):
        yield {
            "session": fake_session,
            "price": fake_price,
            "construct_event": mock_construct,
        }


# ── Celery mock ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_celery_send_task():
    """Always mock celery send_task so tests never enqueue real jobs."""
    with patch("photostore.celery_app.celery_app.send_task") as m:
        yield m
