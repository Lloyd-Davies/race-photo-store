"""Rehearse the current uncommitted migration range on disposable PostgreSQL."""
from pathlib import Path
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text, inspect
from testcontainers.postgres import PostgresContainer

ROOT = Path('/workspace')
with PostgresContainer('postgres:16-alpine') as pg:
    url = pg.get_connection_url().replace('psycopg2', 'psycopg')
    os.environ['DATABASE_URL'] = url
    config = Config(str(ROOT / 'api/alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'api/alembic'))
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, '0009')
    engine = create_engine(url)
    with engine.begin() as db:
        event_id = db.execute(text("INSERT INTO events (slug, name, date, is_password_protected) VALUES ('rehearsal', 'Existing event', now(), false) RETURNING id")).scalar_one()
        db.execute(text("INSERT INTO photos (id, event_id, proof_path, original_path) VALUES ('rehearsal-photo', :event_id, 'proofs/rehearsal/rehearsal-photo.jpg', 'originals/rehearsal/rehearsal-photo.jpg')"), {'event_id': event_id})
    command.upgrade(config, 'head')
    with engine.connect() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0011'
        assert db.execute(text("SELECT name FROM events WHERE slug='rehearsal'")).scalar_one() == 'Existing event'
        assert db.execute(text("SELECT proof_path, original_path, preview_width, preview_height FROM photos WHERE id='rehearsal-photo'")).one() == ('proofs/rehearsal/rehearsal-photo.jpg', 'originals/rehearsal/rehearsal-photo.jpg', None, None)
        assert 'event_asset_migrations' in inspect(db).get_table_names()
    engine.dispose()
print('PASS: disposable 0009 → 0011 upgrade preserves existing event/photo records and adds migration tracking/nullable preview dimensions. Production downgrade is not certified.')
