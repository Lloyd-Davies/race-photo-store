from photostore.models import (
    AssetMigrationStatus,
    AssetType,
    EventAssetMigration,
    EventStatus,
)


def test_storage_migrations_require_admin(client, test_event):
    response = client.get(f"/api/admin/events/{test_event.id}/storage-migrations")
    assert response.status_code == 401


def test_storage_migrations_default_and_queue(
    admin_client,
    db_session,
    test_event,
    test_photos,
    mock_celery_send_task,
):
    initial = admin_client.get(f"/api/admin/events/{test_event.id}/storage-migrations")
    assert initial.status_code == 200
    assert [row["status"] for row in initial.json()["migrations"]] == [
        "NOT_STARTED",
        "NOT_STARTED",
    ]

    queued = admin_client.post(
        f"/api/admin/events/{test_event.id}/storage-migrations/proofs"
    )
    assert queued.status_code == 200
    assert queued.json()["asset_type"] == "PROOFS"
    assert queued.json()["status"] == "QUEUED"
    assert queued.json()["total_count"] == len(test_photos)
    mock_celery_send_task.assert_called_with(
        "tasks.migrate_event_assets.migrate_event_assets",
        args=[test_event.id, "PROOFS"],
    )

    duplicate = admin_client.post(
        f"/api/admin/events/{test_event.id}/storage-migrations/proofs"
    )
    assert duplicate.status_code == 409


def test_failed_storage_migration_can_be_retried(
    admin_client,
    db_session,
    test_event,
    mock_celery_send_task,
):
    migration = EventAssetMigration(
        event_id=test_event.id,
        asset_type=AssetType.PROOFS,
        status=AssetMigrationStatus.FAILED,
        error="temporary error",
    )
    db_session.add(migration)
    db_session.flush()

    response = admin_client.post(
        f"/api/admin/events/{test_event.id}/storage-migrations/proofs"
    )
    assert response.status_code == 200
    db_session.refresh(migration)
    assert migration.status == AssetMigrationStatus.QUEUED
    assert migration.error is None


def test_original_migration_requires_ready_proofs_and_restored_event(
    admin_client,
    db_session,
    test_event,
):
    blocked = admin_client.post(
        f"/api/admin/events/{test_event.id}/storage-migrations/originals"
    )
    assert blocked.status_code == 409

    proof = EventAssetMigration(
        event_id=test_event.id,
        asset_type=AssetType.PROOFS,
        status=AssetMigrationStatus.READY,
    )
    db_session.add(proof)
    test_event.status = EventStatus.ARCHIVED
    db_session.flush()

    archived = admin_client.post(
        f"/api/admin/events/{test_event.id}/storage-migrations/originals"
    )
    assert archived.status_code == 409
    assert "Restore" in archived.json()["detail"]
