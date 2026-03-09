"""Worker test fixtures — shares testcontainers Postgres with API tests."""

import os
import pytest

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("STORAGE_ROOT", "/tmp/photostore-test")
os.environ.setdefault("STRIPE_SECRET_KEY", "")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "")
os.environ.setdefault("STRIPE_PRICE_ID", "")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("EMAIL_ENABLED", "false")
os.environ.setdefault("EMAIL_FROM_ADDRESS", "test@example.com")
os.environ.setdefault("EMAIL_FROM_NAME", "Test Store")
os.environ.setdefault("SUPPORT_EMAIL", "support@example.com")

from testcontainers.postgres import PostgresContainer
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


class _TaskSessionProxy:
    """Wraps a test session so tasks can call commit()/close() safely.

    * commit()  → flush() — makes writes visible within the session but does
                            NOT release the outer test transaction so rollback
                            still cleans up after each test.
    * close()   → no-op  — prevents the task from expiring the session state
                            we still need in assertions.
    All other attribute accesses are forwarded transparently.
    """

    def __init__(self, session):
        object.__setattr__(self, "_session", session)

    def commit(self):
        object.__getattribute__(self, "_session").flush()

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_session"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_session"), name, value)


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_engine(pg_container):
    url = pg_container.get_connection_url().replace("psycopg2", "psycopg")
    os.environ["DATABASE_URL"] = url

    from alembic.config import Config
    from alembic import command
    from pathlib import Path

    engine = create_engine(url, pool_pre_ping=True)
    api_dir = Path(__file__).parent.parent.parent / "api"
    alembic_cfg = Config(str(api_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(api_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    session = TestSession()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    session.begin_nested()
    yield _TaskSessionProxy(session)
    session.close()
    transaction.rollback()
    connection.close()
