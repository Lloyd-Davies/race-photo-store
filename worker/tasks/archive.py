import shutil
import tarfile
from pathlib import Path

import zstandard as zstd

from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.db import SessionLocal
from photostore.models import Event, EventStatus, Photo, PhotoState

ZSTD_COMPRESSION_LEVEL = 3


def _safe_extract_member(member: tarfile.TarInfo, destination: Path) -> None:
    name = member.name

    if name.startswith("/") or name.startswith("\\"):
        raise ValueError(f"Unsafe archive member path: {name}")

    if member.issym() or member.islnk() or member.isdev():
        raise ValueError(f"Unsafe archive member type: {name}")

    target_path = (destination / name).resolve()
    destination_root = destination.resolve()
    if target_path != destination_root and destination_root not in target_path.parents:
        raise ValueError(f"Archive member escapes destination: {name}")


def _safe_extract_tar_stream(tar: tarfile.TarFile, destination: Path) -> None:
    for member in tar:
        _safe_extract_member(member, destination)
        tar.extract(member, path=destination)


@celery_app.task(name="tasks.archive.archive_event")
def archive_event(event_id: int) -> None:
    db = SessionLocal()
    try:
        event: Event | None = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise ValueError(f"Event {event_id} not found")

        storage_root = Path(settings.STORAGE_ROOT)
        originals_dir = storage_root / "originals" / event.slug
        archive_dir = storage_root / "archive"
        archive_path = archive_dir / f"{event.slug}.tar.zst"

        if not originals_dir.exists():
            raise FileNotFoundError(f"Originals directory not found: {originals_dir}")

        archive_dir.mkdir(parents=True, exist_ok=True)

        # Stream originals into a zstd-compressed tar archive
        cctx = zstd.ZstdCompressor(level=ZSTD_COMPRESSION_LEVEL)
        with open(archive_path, "wb") as fh:
            with cctx.stream_writer(fh, closefd=False) as writer:
                with tarfile.open(fileobj=writer, mode="w|") as tar:  # type: ignore[arg-type]
                    tar.add(originals_dir, arcname=event.slug)

        # Remove originals only after successful archive
        shutil.rmtree(originals_dir)

        # Update photo states
        db.query(Photo).filter(Photo.event_id == event_id).update(
            {Photo.state: PhotoState.ARCHIVED_ONLY}
        )
        event.status = EventStatus.ARCHIVED
        db.commit()

    finally:
        db.close()


@celery_app.task(name="tasks.archive.restore_event")
def restore_event(event_id: int) -> None:
    db = SessionLocal()
    try:
        event: Event | None = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            raise ValueError(f"Event {event_id} not found")

        storage_root = Path(settings.STORAGE_ROOT)
        archive_path = storage_root / "archive" / f"{event.slug}.tar.zst"
        originals_parent = storage_root / "originals"

        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        originals_parent.mkdir(parents=True, exist_ok=True)

        # Decompress and extract
        dctx = zstd.ZstdDecompressor()
        with open(archive_path, "rb") as fh:
            with dctx.stream_reader(fh) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as tar:  # type: ignore[arg-type]
                    _safe_extract_tar_stream(tar, originals_parent)

        # Update photo states back to READY
        db.query(Photo).filter(Photo.event_id == event_id).update(
            {Photo.state: PhotoState.READY}
        )
        event.status = EventStatus.ACTIVE
        db.commit()

    finally:
        db.close()
