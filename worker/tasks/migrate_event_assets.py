from datetime import datetime, timezone

from photostore.celery_app import celery_app
from photostore.db import SessionLocal
from photostore.models import (
    AssetMigrationStatus,
    AssetType,
    Event,
    EventAssetMigration,
    EventStatus,
    Photo,
)
from photostore.storage import LocalStorageBackend, R2StorageBackend

MIGRATION_ERROR_MAX_LENGTH = 1000


def _migration_path(photo: Photo, asset_type: AssetType) -> str:
    return photo.proof_path if asset_type == AssetType.PROOFS else photo.original_path


@celery_app.task(name="tasks.migrate_event_assets.migrate_event_assets")
def migrate_event_assets(event_id: int, asset_type_value: str) -> None:
    db = SessionLocal()
    migration = None
    try:
        asset_type = AssetType(asset_type_value)
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise ValueError(f"Event {event_id} not found")

        migration = (
            db.query(EventAssetMigration)
            .filter(
                EventAssetMigration.event_id == event_id,
                EventAssetMigration.asset_type == asset_type,
            )
            .first()
        )
        if not migration:
            raise ValueError(f"Migration {event_id}/{asset_type.value} not found")

        if asset_type == AssetType.ORIGINALS:
            proof_migration = (
                db.query(EventAssetMigration)
                .filter(
                    EventAssetMigration.event_id == event_id,
                    EventAssetMigration.asset_type == AssetType.PROOFS,
                )
                .first()
            )
            if not proof_migration or proof_migration.status != AssetMigrationStatus.READY:
                raise ValueError("Proof migration must be ready before originals")
            if event.status == EventStatus.ARCHIVED:
                raise ValueError("Archived events must be restored before migrating originals")

        photos = (
            db.query(Photo)
            .filter(Photo.event_id == event_id)
            .order_by(Photo.id.asc())
            .all()
        )
        migration.status = AssetMigrationStatus.RUNNING
        migration.total_count = len(photos)
        migration.migrated_count = 0
        migration.skipped_count = 0
        migration.failed_count = 0
        migration.started_at = datetime.now(timezone.utc)
        migration.completed_at = None
        migration.error = None
        db.commit()

        local_storage = LocalStorageBackend()
        r2_storage = R2StorageBackend()
        errors: list[str] = []

        for photo in photos:
            key = _migration_path(photo, asset_type)
            try:
                if r2_storage.exists(key):
                    migration.skipped_count += 1
                else:
                    local_path = local_storage.local_path(key)
                    if not local_path.exists():
                        raise FileNotFoundError(f"Local source not found: {key}")
                    r2_storage.upload_file(local_path, key, content_type="image/jpeg")
                    if not r2_storage.exists(key):
                        raise RuntimeError(f"Object verification failed: {key}")
                    migration.migrated_count += 1
            except Exception as exc:
                migration.failed_count += 1
                if len(errors) < 5:
                    errors.append(f"{photo.id}: {exc}")
            db.commit()

        migration.completed_at = datetime.now(timezone.utc)
        if migration.failed_count:
            migration.status = AssetMigrationStatus.FAILED
            migration.error = "; ".join(errors)[:MIGRATION_ERROR_MAX_LENGTH]
        else:
            migration.status = AssetMigrationStatus.READY
            migration.error = None
        db.commit()

    except Exception as exc:
        if migration is not None:
            migration.status = AssetMigrationStatus.FAILED
            migration.completed_at = datetime.now(timezone.utc)
            migration.error = str(exc)[:MIGRATION_ERROR_MAX_LENGTH]
            db.commit()
        raise
    finally:
        db.close()
