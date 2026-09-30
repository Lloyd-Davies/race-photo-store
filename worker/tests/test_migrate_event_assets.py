import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from photostore.models import (
    AssetMigrationStatus,
    AssetType,
    Event,
    EventAssetMigration,
    Photo,
)


def _module():
    if "worker.tasks.migrate_event_assets" not in sys.modules:
        importlib.import_module("worker.tasks.migrate_event_assets")
    return sys.modules["worker.tasks.migrate_event_assets"]


class FakeR2:
    def __init__(self):
        self.objects = set()
        self.uploads = []

    def exists(self, key):
        return key in self.objects

    def upload_file(self, source, key, content_type=None):
        assert Path(source).exists()
        self.objects.add(key)
        self.uploads.append((key, content_type))


def _seed(db_session, storage: Path):
    event = Event(
        slug="asset-migration",
        name="Asset Migration",
        date=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()
    for index in range(2):
        photo_id = f"asset-{index}"
        proof_path = f"proofs/{event.slug}/{photo_id}.jpg"
        original_path = f"originals/{event.slug}/{photo_id}.jpg"
        for key in (proof_path, original_path):
            path = storage / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(key.encode("ascii"))
        db_session.add(Photo(
            id=photo_id,
            event_id=event.id,
            proof_path=proof_path,
            original_path=original_path,
        ))
    migration = EventAssetMigration(
        event_id=event.id,
        asset_type=AssetType.PROOFS,
        status=AssetMigrationStatus.QUEUED,
    )
    db_session.add(migration)
    db_session.flush()
    return event, migration


def test_proof_migration_is_idempotent_and_keeps_local_files(
    db_session, tmp_path, monkeypatch
):
    from photostore.config import settings

    module = _module()
    storage = tmp_path / "photos"
    event, migration = _seed(db_session, storage)
    r2 = FakeR2()
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(module, "R2StorageBackend", lambda: r2)

    module.migrate_event_assets.apply(args=[event.id, "PROOFS"]).get()
    db_session.refresh(migration)
    assert migration.status == AssetMigrationStatus.READY
    assert migration.migrated_count == 2
    assert migration.failed_count == 0
    assert all((storage / key).exists() for key in r2.objects)

    module.migrate_event_assets.apply(args=[event.id, "PROOFS"]).get()
    db_session.refresh(migration)
    assert migration.status == AssetMigrationStatus.READY
    assert migration.migrated_count == 0
    assert migration.skipped_count == 2
    assert len(r2.uploads) == 2


def test_migration_failure_is_reported_without_deleting_local_files(
    db_session, tmp_path, monkeypatch
):
    from photostore.config import settings

    module = _module()
    storage = tmp_path / "photos"
    event, migration = _seed(db_session, storage)
    missing = storage / f"proofs/{event.slug}/asset-1.jpg"
    missing.unlink()
    r2 = FakeR2()
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(module, "R2StorageBackend", lambda: r2)

    module.migrate_event_assets.apply(args=[event.id, "PROOFS"]).get()
    db_session.refresh(migration)
    assert migration.status == AssetMigrationStatus.FAILED
    assert migration.failed_count == 1
    assert "Local source not found" in migration.error
    assert (storage / f"proofs/{event.slug}/asset-0.jpg").exists()


def test_original_migration_runs_after_proofs_are_ready(
    db_session, tmp_path, monkeypatch
):
    from photostore.config import settings

    module = _module()
    storage = tmp_path / "photos"
    event, proof_migration = _seed(db_session, storage)
    proof_migration.status = AssetMigrationStatus.READY
    original_migration = EventAssetMigration(
        event_id=event.id,
        asset_type=AssetType.ORIGINALS,
        status=AssetMigrationStatus.QUEUED,
    )
    db_session.add(original_migration)
    db_session.flush()
    r2 = FakeR2()
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(module, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(module, "R2StorageBackend", lambda: r2)

    module.migrate_event_assets.apply(args=[event.id, "ORIGINALS"]).get()
    db_session.refresh(original_migration)
    assert original_migration.status == AssetMigrationStatus.READY
    assert {key for key, _ in r2.uploads} == {
        f"originals/{event.slug}/asset-0.jpg",
        f"originals/{event.slug}/asset-1.jpg",
    }
