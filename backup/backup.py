"""Independent encrypted PostgreSQL backups and guarded disposable restore drills."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
import psycopg
from psycopg import sql


def required(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise ValueError(f'Missing setting: {name}')
    return value


def storage():
    endpoint = required('BACKUP_R2_ENDPOINT')
    if not endpoint.startswith('https://') and endpoint != 'http://127.0.0.1:5000':
        raise ValueError('Backup endpoint must use HTTPS (only local emulator permits HTTP)')
    return boto3.client('s3', endpoint_url=endpoint, region_name='auto',
        aws_access_key_id=required('BACKUP_R2_ACCESS_KEY_ID'),
        aws_secret_access_key=required('BACKUP_R2_SECRET_ACCESS_KEY'),
        config=Config(connect_timeout=10, read_timeout=30,
                      request_checksum_calculation='when_required',
                      response_checksum_validation='when_required',
                      retries={'total_max_attempts': 4, 'mode': 'standard'},
                      s3={'addressing_style': 'path'}))


def pg_env(host=None, database=None):
    env = os.environ.copy()
    env.update(PGHOST=host or required('BACKUP_PGHOST'),
               PGDATABASE=database or required('BACKUP_PGDATABASE'),
               PGUSER=required('BACKUP_PGUSER'), PGPASSWORD=required('BACKUP_PGPASSWORD'),
               PGPORT=os.environ.get('BACKUP_PGPORT', '5432'), PGCONNECT_TIMEOUT='10')
    return env


def connect(host=None, database=None):
    e = pg_env(host, database)
    return psycopg.connect(host=e['PGHOST'], port=e['PGPORT'], dbname=e['PGDATABASE'],
                           user=e['PGUSER'], password=e['PGPASSWORD'], connect_timeout=10)


def run(args, env=None):
    # Never emit pg/age error output: it may contain source data or credentials.
    subprocess.run(args, env=env, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ping(suffix=''):
    url = os.environ.get('BACKUP_HEALTHCHECK_URL', '')
    if not url:
        if os.environ.get('BACKUP_LOCAL_TEST') == '1':
            return
        raise ValueError('Missing setting: BACKUP_HEALTHCHECK_URL')
    if not re.fullmatch(r'https://hc-ping\.com/[0-9a-f-]{36}', url):
        raise ValueError('Invalid monitoring URL')
    req = urllib.request.Request(url + suffix, data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError('Monitoring ping failed')


@contextmanager
def workspace():
    root = Path(os.environ.get('BACKUP_WORK_DIR', '/work'))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    with open(root / 'job.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('A backup or restore is already running') from None
        # Only our own temporary directories; remove leftovers after abrupt termination.
        for previous in root.glob('attempt-*'):
            if previous.is_dir() and not previous.is_symlink():
                shutil.rmtree(previous)
        with tempfile.TemporaryDirectory(prefix='attempt-', dir=root) as directory:
            os.chmod(directory, 0o700)
            yield Path(directory)


@contextmanager
def deadline():
    def expired(*_):
        raise TimeoutError('Job exceeded one hour')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(3600)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def transfer(operation):
    for attempt in range(4):
        try:
            return operation()
        except (BotoCoreError, ClientError) as exc:
            if isinstance(exc, ClientError):
                status = exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode', 0)
                if status < 500 and status not in (408, 429):
                    raise
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def backup():
    with workspace() as work, deadline():
        ping('/start')
        try:
            plain, encrypted, verified = (work / n for n in ('db.dump', 'db.dump.age', 'verify.age'))
            with connect() as db:
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                snapshot_at = datetime.now(timezone.utc).isoformat()
                size, version = db.execute('SELECT pg_database_size(current_database()), version()').fetchone()
                revision = db.execute('SELECT version_num FROM alembic_version ORDER BY version_num').fetchall()
                if shutil.disk_usage(work).free < size * 4 + 256 * 1024 * 1024:
                    raise RuntimeError('Insufficient backup working space')
                snapshot = db.execute('SELECT pg_export_snapshot()').fetchone()[0]
                run(['pg_dump', '--format=custom', '--file', str(plain),
                     '--lock-wait-timeout=30s', '--snapshot', snapshot], pg_env())
            run(['pg_restore', '--list', str(plain)])
            run(['age', '--recipient', required('BACKUP_AGE_RECIPIENT'), '--output', str(encrypted), str(plain)])
            plain.unlink()
            timestamp = datetime.now(timezone.utc)
            key = f'database/{timestamp:%Y/%m/%d}/{timestamp:%H%M%S}-{uuid.uuid4().hex}.dump.age'
            client, bucket = storage(), required('BACKUP_R2_BUCKET')
            transfer(lambda: client.upload_file(str(encrypted), bucket, key))
            transfer(lambda: client.download_file(bucket, key, str(verified)))
            if digest(encrypted) != digest(verified):
                raise RuntimeError('Uploaded backup checksum mismatch')
            manifest = {'format_version': 1, 'object_key': key, 'completed_at': timestamp.isoformat(),
                'snapshot_at': snapshot_at,
                'sha256': digest(encrypted), 'size_bytes': encrypted.stat().st_size,
                'postgres_version': version, 'schema_revisions': [r[0] for r in revision],
                'application_images_source': 'operator_observed',
                'application_images': json.loads(required('BACKUP_APPLICATION_IMAGES'))}
            # Supplied operator observations; no socket access to inspect application containers.
            transfer(lambda: client.put_object(Bucket=bucket, Key=key + '.json',
                Body=json.dumps(manifest).encode(), ContentType='application/json'))
            stored = transfer(lambda: client.get_object(Bucket=bucket, Key=key + '.json'))
            if json.loads(stored['Body'].read()) != manifest:
                raise RuntimeError('Manifest verification failed')
            ping()
            print(json.dumps({'result': 'verified', 'manifest': key + '.json',
                              'size_bytes': manifest['size_bytes']}), flush=True)
            return manifest
        except Exception:
            try:
                ping('/fail')
            except Exception:
                pass  # External missed-success detection still catches a stopped job.
            raise


def restore(manifest_key, identity):
    if not re.fullmatch(r'database/\d{4}/\d{2}/\d{2}/[0-9]{6}-[0-9a-f]{32}\.dump\.age\.json', manifest_key):
        raise ValueError('Select a generated backup manifest key')
    # Restore has no caller-controlled host or existing destination database.
    host = 'restore-postgres'
    with connect(host, 'postgres') as db:
        if not db.execute("SELECT 1 FROM pg_database WHERE datname='backup_drill_guard'").fetchone():
            raise ValueError('Destination is not an isolated restore-drill cluster')
    database = 'drill_' + uuid.uuid4().hex
    with workspace() as work, deadline():
        client, bucket = storage(), required('BACKUP_R2_BUCKET')
        response = transfer(lambda: client.get_object(Bucket=bucket, Key=manifest_key))
        manifest = json.loads(response['Body'].read())
        if manifest.get('format_version') != 1 or manifest.get('object_key') + '.json' != manifest_key:
            raise ValueError('Invalid backup manifest')
        if shutil.disk_usage(work).free < manifest['size_bytes'] * 8 + 256 * 1024 * 1024:
            raise RuntimeError('Insufficient restore working space')
        encrypted, plain = work / 'db.age', work / 'db.dump'
        transfer(lambda: client.download_file(bucket, manifest['object_key'], str(encrypted)))
        if encrypted.stat().st_size != manifest['size_bytes'] or digest(encrypted) != manifest['sha256']:
            raise RuntimeError('Backup checksum mismatch')
        run(['age', '--decrypt', '--identity', identity, '--output', str(plain), str(encrypted)])
        run(['pg_restore', '--list', str(plain)])
        with connect(host, 'postgres') as db:
            db.autocommit = True
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        # Failure leaves this new disposable DB for inspection; never touches an existing DB.
        run(['pg_restore', '--dbname', database, '--exit-on-error', '--single-transaction', '--no-owner', '--no-acl', str(plain)],
            pg_env(host, database))
        with connect(host, database) as db:
            revisions = [r[0] for r in db.execute('SELECT version_num FROM alembic_version ORDER BY version_num')]
        if revisions != manifest['schema_revisions']:
            raise RuntimeError('Restored schema differs from manifest')
        print(json.dumps({'result': 'restored', 'database': database, 'schema_revisions': revisions}), flush=True)
        return database


def next_run(now):
    now = now.astimezone(timezone.utc)
    for day in (0, 1):
        for hour in (2, 14):
            target = (now + timedelta(days=day)).replace(hour=hour, minute=0, second=0, microsecond=0)
            if target > now:
                return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['once', 'schedule', 'restore'])
    parser.add_argument('--manifest')
    parser.add_argument('--identity')
    args = parser.parse_args()
    if args.command == 'restore':
        if not args.manifest or not args.identity:
            parser.error('restore requires --manifest and --identity')
        restore(args.manifest, args.identity)
    elif args.command == 'once':
        backup()
    else:
        while True:
            try:
                backup()
            except Exception as exc:
                print(json.dumps({'result': 'failed', 'error_type': type(exc).__name__}), flush=True)
            target = next_run(datetime.now(timezone.utc))
            while datetime.now(timezone.utc) < target:
                time.sleep(min(30, (target - datetime.now(timezone.utc)).total_seconds()))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'result': 'failed', 'error_type': type(exc).__name__}), flush=True)
        raise SystemExit(1)
