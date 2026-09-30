from unittest.mock import Mock

import pytest

from photostore.models import AssetMigrationStatus, AssetType, Event, EventAssetMigration, Photo


@pytest.mark.parametrize('setting,path_attr', [
    ('PROOF_STORAGE_BACKEND', 'proof_path'), ('ORIGINAL_STORAGE_BACKEND', 'original_path'),
])
def test_delete_removes_direct_r2_uploads_without_migration_rows(
    admin_client, test_event, test_photos, monkeypatch, setting, path_attr
):
    from app.routes import admin
    from photostore.config import settings
    remote = Mock()
    monkeypatch.setattr(settings, setting, 'r2')
    monkeypatch.setattr(admin, 'R2StorageBackend', lambda: remote)
    expected = {getattr(photo, path_attr) for photo in test_photos}
    response = admin_client.delete(f'/api/admin/events/{test_event.id}?delete_files=true')
    assert response.status_code == 200
    assert {call.args[0] for call in remote.delete.call_args_list} == expected


def test_failed_migration_cleans_possible_upload_before_progress_was_saved(
    admin_client, db_session, test_event, test_photos, monkeypatch
):
    from app.routes import admin
    remote = Mock()
    monkeypatch.setattr(admin, 'R2StorageBackend', lambda: remote)
    db_session.add(EventAssetMigration(event_id=test_event.id, asset_type=AssetType.PROOFS,
        status=AssetMigrationStatus.FAILED, migrated_count=0, skipped_count=0))
    db_session.flush()
    response = admin_client.delete(f'/api/admin/events/{test_event.id}?delete_files=true')
    assert response.status_code == 200
    assert remote.delete.call_count == len(test_photos)


@pytest.mark.parametrize('status', [AssetMigrationStatus.QUEUED, AssetMigrationStatus.RUNNING])
def test_active_migration_blocks_deletion_even_with_force(
    admin_client, db_session, test_event, test_photos, status, monkeypatch
):
    from app.routes import admin
    remote = Mock()
    monkeypatch.setattr(admin, 'R2StorageBackend', lambda: remote)
    db_session.add(EventAssetMigration(event_id=test_event.id, asset_type=AssetType.PROOFS, status=status))
    db_session.flush()
    response = admin_client.delete(f'/api/admin/events/{test_event.id}?delete_files=true&force=true')
    assert response.status_code == 409
    assert db_session.get(Event, test_event.id) is not None
    assert db_session.query(Photo).filter(Photo.event_id == test_event.id).count() == len(test_photos)
    remote.delete.assert_not_called()
