"""Tests for the archive and restore Celery tasks.

Tasks are invoked via .apply() for synchronous eager execution.
SessionLocal is monkeypatched to return the test's transactional session.
"""

from datetime import datetime, timezone
from pathlib import Path

from photostore.models import Event, EventStatus, Photo, PhotoState


def _seed_event(db_session, storage: Path, with_originals=True, with_archive=False):
    """Create event + photos on disk. Returns the Event ORM object."""
    event = Event(
        slug="archive-test",
        name="Archive Test Race",
        date=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    photo_ids = [f"arch-photo-{i}" for i in range(1, 4)]
    for pid in photo_ids:
        proof = storage / "proofs" / event.slug / f"{pid}.jpg"
        proof.parent.mkdir(parents=True, exist_ok=True)
        proof.write_bytes(b"FAKEJPEG_PROOF")

        if with_originals:
            original = storage / "originals" / event.slug / f"{pid}.jpg"
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(b"FAKEJPEG_ORIGINAL")

        db_session.add(Photo(
            id=pid,
            event_id=event.id,
            proof_path=f"proofs/{event.slug}/{pid}.jpg",
            original_path=f"originals/{event.slug}/{pid}.jpg",
            state=PhotoState.READY,
        ))

    db_session.flush()

    if with_archive:
        # Pre-build a real .tar.zst archive so restore tests can run
        import tarfile
        import zstandard as zstd
        archive_dir = storage / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{event.slug}.tar.zst"
        originals_dir = storage / "originals" / event.slug
        cctx = zstd.ZstdCompressor(level=3)
        with open(archive_path, "wb") as fh:
            with cctx.stream_writer(fh, closefd=False) as writer:
                with tarfile.open(fileobj=writer, mode="w|") as tar:  # type: ignore[arg-type]
                    tar.add(originals_dir, arcname=event.slug)

    return event


# ---------------------------------------------------------------------------
# archive_event
# ---------------------------------------------------------------------------

def test_archive_event_creates_tar_zst(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage)
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    arch_module.archive_event.apply(args=[event.id])

    archive_path = storage / "archive" / f"{event.slug}.tar.zst"
    assert archive_path.exists()
    assert archive_path.stat().st_size > 0


def test_archive_event_removes_originals_dir(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage)
    originals_dir = storage / "originals" / event.slug
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    assert originals_dir.exists()
    arch_module.archive_event.apply(args=[event.id])
    assert not originals_dir.exists()


def test_archive_event_marks_event_archived(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage)
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    arch_module.archive_event.apply(args=[event.id])

    db_session.refresh(event)
    assert event.status == EventStatus.ARCHIVED


def test_archive_event_updates_photo_states(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage)
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    arch_module.archive_event.apply(args=[event.id])

    photos = db_session.query(Photo).filter(Photo.event_id == event.id).all()
    assert all(p.state == PhotoState.ARCHIVED_ONLY for p in photos)


def test_archive_event_missing_originals_raises(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage, with_originals=False)
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    result = arch_module.archive_event.apply(args=[event.id])
    assert result.failed()


# ---------------------------------------------------------------------------
# restore_event
# ---------------------------------------------------------------------------

def test_restore_event_extracts_originals(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage, with_originals=True, with_archive=True)
    import shutil
    shutil.rmtree(storage / "originals" / event.slug)

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    arch_module.restore_event.apply(args=[event.id])

    restored_dir = storage / "originals" / event.slug
    assert restored_dir.exists()
    assert len(list(restored_dir.iterdir())) == 3


def test_restore_event_marks_photos_ready(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage, with_originals=True, with_archive=True)
    import shutil
    shutil.rmtree(storage / "originals" / event.slug)

    db_session.query(Photo).filter(Photo.event_id == event.id).update(
        {Photo.state: PhotoState.ARCHIVED_ONLY}
    )
    db_session.flush()

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    arch_module.restore_event.apply(args=[event.id])

    photos = db_session.query(Photo).filter(Photo.event_id == event.id).all()
    assert all(p.state == PhotoState.READY for p in photos)


def test_restore_event_missing_archive_raises(db_session, tmp_path, monkeypatch):
    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage, with_originals=False, with_archive=False)
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    result = arch_module.restore_event.apply(args=[event.id])
    assert result.failed()


def test_restore_event_rejects_path_traversal_members(db_session, tmp_path, monkeypatch):
    import io
    import tarfile
    import zstandard as zstd

    from photostore.config import settings
    from worker.tasks import archive as arch_module

    storage = tmp_path / "photos"
    event = _seed_event(db_session, storage, with_originals=False, with_archive=False)

    archive_dir = storage / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{event.slug}.tar.zst"

    cctx = zstd.ZstdCompressor(level=3)
    with open(archive_path, "wb") as fh:
        with cctx.stream_writer(fh, closefd=False) as writer:
            with tarfile.open(fileobj=writer, mode="w|") as tar:  # type: ignore[arg-type]
                payload = b"owned"
                info = tarfile.TarInfo(name="../escape.txt")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))

    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage))
    monkeypatch.setattr(arch_module, "SessionLocal", lambda: db_session)

    outside = storage / "escape.txt"
    result = arch_module.restore_event.apply(args=[event.id])
    assert result.failed()
    assert not outside.exists()
