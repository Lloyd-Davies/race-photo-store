from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import os
from unittest.mock import patch

from botocore.exceptions import ClientError
from moto.server import ThreadedMotoServer
import pytest
import yaml

import backup as b
from alembic import command
from alembic.config import Config


@pytest.fixture(scope='module', autouse=True)
def infrastructure():
    server = ThreadedMotoServer(ip_address='127.0.0.1', port=5000, verbose=False)
    server.start()
    b.storage().create_bucket(Bucket='backup-test', CreateBucketConfiguration={'LocationConstraint': 'auto'})
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://postgres:local-backup-test@postgres/source'
    cfg = Config()
    cfg.set_main_option('script_location', '/app/migrations')
    command.upgrade(cfg, 'head')
    with b.connect() as db:
        db.execute('''
          INSERT INTO events(slug,name,date,is_password_protected) VALUES ('synthetic','Synthetic',now(),false);
          INSERT INTO photos(id,event_id,proof_path,original_path) VALUES ('synthetic-photo',1,'proofs/synthetic/a.jpg','originals/synthetic/a.jpg');
          INSERT INTO photo_tags(photo_id,tag_type,value) VALUES ('synthetic-photo','bib','123');
          INSERT INTO orders(stripe_session_id,email,status,currency,stripe_amount_refunded_pence,stripe_pricing_status) VALUES ('synthetic','synthetic@example.invalid','READY','GBP',0,'UNSYNCED');
          INSERT INTO order_items(order_id,photo_id,unit_price_pence) VALUES (1,'synthetic-photo',500);
        ''')
    with b.connect(database='postgres') as db:
        db.autocommit = True
        db.execute('CREATE DATABASE backup_drill_guard')
    yield
    server.stop()


@pytest.fixture
def key(tmp_path, monkeypatch):
    identity = tmp_path / 'key.agekey'
    subprocess.run(['age-keygen', '-o', str(identity)], check=True, capture_output=True)
    public = subprocess.check_output(['age-keygen', '-y', str(identity)], text=True).strip()
    monkeypatch.setenv('BACKUP_AGE_RECIPIENT', public)
    return str(identity)


def test_roundtrip_relationships_sequences_schema_and_cleanup(key):
    manifest = b.backup()
    name = b.restore(manifest['object_key'] + '.json', key)
    with b.connect('restore-postgres', name) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '0011'
        assert db.execute('SELECT value FROM photo_tags JOIN photos ON photos.id=photo_tags.photo_id JOIN events ON events.id=photos.event_id').fetchone()[0] == '123'
        assert db.execute('SELECT status FROM orders JOIN order_items ON orders.id=order_items.order_id').fetchone()[0] == 'READY'
        assert db.execute("INSERT INTO events(slug,name,date,is_password_protected) VALUES ('after-restore','Restored',now(),false) RETURNING id").fetchone()[0] == 2
        with pytest.raises(Exception):
            db.execute("INSERT INTO photos(id,event_id,proof_path,original_path) VALUES ('invalid',9999,'proof','original')")
    assert not list(Path('/work').glob('attempt-*'))
    assert manifest['size_bytes'] > 0
    assert manifest['application_images']['api'] == 'local-test'


def test_wrong_key_refused_before_creating_database(key, tmp_path):
    manifest = b.backup()
    other = tmp_path / 'wrong.agekey'
    subprocess.run(['age-keygen', '-o', str(other)], check=True, capture_output=True)
    with b.connect(database='postgres') as db:
        before = db.execute('SELECT count(*) FROM pg_database').fetchone()[0]
    with pytest.raises(subprocess.CalledProcessError):
        b.restore(manifest['object_key'] + '.json', str(other))
    with b.connect(database='postgres') as db:
        assert db.execute('SELECT count(*) FROM pg_database').fetchone()[0] == before


def test_corrupt_remote_backup_refused(key):
    manifest = b.backup()
    b.storage().put_object(Bucket='backup-test', Key=manifest['object_key'], Body=b'corrupt')
    with pytest.raises(RuntimeError, match='checksum'):
        b.restore(manifest['object_key'] + '.json', key)


def test_missing_guard_refused(key):
    manifest = b.backup()
    with b.connect(database='postgres') as db:
        db.autocommit = True
        db.execute('ALTER DATABASE backup_drill_guard RENAME TO temporarily_hidden')
    try:
        with pytest.raises(ValueError, match='isolated'):
            b.restore(manifest['object_key'] + '.json', key)
    finally:
        with b.connect(database='postgres') as db:
            db.autocommit = True
            db.execute('ALTER DATABASE temporarily_hidden RENAME TO backup_drill_guard')


def test_upload_checksum_failure_sends_failure_not_success(key):
    client = b.storage()
    client.download_file = lambda bucket, key, path: Path(path).write_bytes(b'corrupt')
    with patch.object(b, 'storage', return_value=client), patch.object(b, 'ping') as ping:
        with pytest.raises(RuntimeError, match='checksum'):
            b.backup()
    assert [call.args for call in ping.call_args_list] == [('/start',), ('/fail',)]


def test_database_unavailable_sends_failure(key, monkeypatch):
    monkeypatch.setenv('BACKUP_PGHOST', '127.0.0.1')
    with patch.object(b, 'ping') as ping:
        with pytest.raises(Exception):
            b.backup()
    assert ping.call_args.args == ('/fail',)


def test_insufficient_disk(key):
    with patch.object(b.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 0})()):
        with pytest.raises(RuntimeError, match='space'):
            b.backup()


def test_overlap_refused():
    with b.workspace():
        with pytest.raises(RuntimeError, match='already running'):
            with b.workspace():
                pass


def test_transient_upload_retries_and_permanent_failure_does_not():
    transient = ClientError({'Error': {'Code': 'InternalError'}, 'ResponseMetadata': {'HTTPStatusCode': 503}}, 'PutObject')
    permanent = ClientError({'Error': {'Code': 'AccessDenied'}, 'ResponseMetadata': {'HTTPStatusCode': 403}}, 'PutObject')
    with patch.object(b.time, 'sleep'), patch('builtins.print'):
        with patch.object(b, 'storage') as operation:
            operation.side_effect = [transient, transient, 'ok']
            assert b.transfer(operation) == 'ok'
            assert operation.call_count == 3
        with patch.object(b, 'storage') as operation:
            operation.side_effect = permanent
            with pytest.raises(ClientError):
                b.transfer(operation)
            assert operation.call_count == 1


def test_monitoring_no_customer_data_and_missing_success_detection_configuration(monkeypatch):
    monkeypatch.setenv('BACKUP_HEALTHCHECK_URL', 'https://hc-ping.com/00000000-0000-0000-0000-000000000000')
    with patch.object(b.urllib.request, 'urlopen') as send:
        send.return_value.__enter__.return_value.status = 200
        b.ping('/fail')
        request = send.call_args.args[0]
        assert request.data == b''
        assert request.full_url.endswith('/fail')
    monkeypatch.delenv('BACKUP_HEALTHCHECK_URL')
    monkeypatch.delenv('BACKUP_LOCAL_TEST')
    with pytest.raises(ValueError, match='HEALTHCHECK'):
        b.ping()


@pytest.mark.parametrize('hour,expected_day,expected_hour', [(1,1,2),(2,1,14),(13,1,14),(14,2,2),(23,2,2)])
def test_utc_schedule(hour, expected_day, expected_hour):
    result = b.next_run(datetime(2026, 10, 1, hour, tzinfo=timezone.utc))
    assert (result.day,result.hour) == (expected_day,expected_hour)


def test_existing_or_arbitrary_restore_destination_not_accepted():
    with pytest.raises(ValueError, match='manifest'):
        b.restore('production', '/missing')


def test_exhausted_upload_fails_and_cleans_work(key):
    client = b.storage()
    client.upload_file = lambda *_: (_ for _ in ()).throw(ClientError(
        {'Error': {'Code': 'InternalError'}, 'ResponseMetadata': {'HTTPStatusCode': 503}}, 'PutObject'))
    with patch.object(b, 'storage', return_value=client), patch.object(b, 'ping') as ping, patch.object(b.time, 'sleep'):
        with pytest.raises(ClientError):
            b.backup()
    assert ping.call_args.args == ('/fail',)
    assert not list(Path('/work').glob('attempt-*'))


def test_abandoned_work_removed_and_timeout_armed():
    stale = Path('/work/attempt-abandoned')
    stale.mkdir()
    (stale / 'partial.dump').write_bytes(b'synthetic')
    with b.workspace():
        assert not stale.exists()
    with patch.object(b.signal, 'alarm') as alarm:
        with b.deadline():
            assert alarm.call_args.args == (3600,)
        assert alarm.call_args.args == (0,)


def test_deployment_and_restore_isolation():
    production = yaml.safe_load(Path('/app/definitions/production.yml').read_text())
    service = production['services']['backup']
    assert service['volumes'] == ['backup-work:/work']
    assert service['read_only'] is True
    assert 'BACKUP_IMAGE_TAG' in service['image']
    assert not any('IDENTITY' in key for key in service['environment'])
    restore = yaml.safe_load(Path('/app/definitions/compose.restore.yml').read_text())
    assert set(restore['services']) == {'restore-postgres', 'restore'}
    assert 'ports' not in restore['services']['restore-postgres']
    assert restore['networks']['database']['internal'] is True
    rules = json.loads(Path('/app/definitions/r2-lifecycle.json').read_text())['Rules'][0]
    assert rules['Filter']['Prefix'] == 'database/'
    assert rules['Expiration']['Days'] == 30
