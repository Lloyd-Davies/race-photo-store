from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin
from app.schemas import (
    BibTagsRequest,
    BibTagsResult,
    CreateEventRequest,
    EventCreatedOut,
    IngestResult,
)
from photostore.config import settings
from photostore.models import Event, Photo, PhotoState, PhotoTag

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/events", response_model=EventCreatedOut, dependencies=[Depends(require_admin)])
def create_event(req: CreateEventRequest, db: Session = Depends(get_db)) -> EventCreatedOut:
    if db.query(Event).filter(Event.slug == req.slug).first():
        raise HTTPException(409, f"Event slug '{req.slug}' already exists")

    event = Event(
        slug=req.slug,
        name=req.name,
        date=req.date,
        location=req.location,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return EventCreatedOut(id=event.id, slug=event.slug)


@router.post(
    "/events/{event_id}/ingest",
    response_model=IngestResult,
    dependencies=[Depends(require_admin)],
)
def ingest_photos(event_id: int, db: Session = Depends(get_db)) -> IngestResult:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    storage_root = Path(settings.STORAGE_ROOT)
    proofs_dir = storage_root / "proofs" / event.slug

    if not proofs_dir.exists():
        raise HTTPException(
            404,
            f"Proofs directory not found at: {proofs_dir}. "
            "Ensure proof images are uploaded before ingesting.",
        )

    ingested = 0
    skipped = 0

    for filepath in sorted(proofs_dir.glob("*.jpg")):
        photo_id = filepath.stem

        if db.query(Photo).filter(Photo.id == photo_id).first():
            skipped += 1
            continue

        original = storage_root / "originals" / event.slug / f"{photo_id}.jpg"
        state = PhotoState.READY if original.exists() else PhotoState.MISSING

        db.add(
            Photo(
                id=photo_id,
                event_id=event_id,
                proof_path=f"proofs/{event.slug}/{photo_id}.jpg",
                original_path=f"originals/{event.slug}/{photo_id}.jpg",
                state=state,
            )
        )
        ingested += 1

    db.commit()
    return IngestResult(ingested=ingested, skipped=skipped)


@router.post(
    "/events/{event_id}/tags/bibs",
    response_model=BibTagsResult,
    dependencies=[Depends(require_admin)],
)
def upload_bib_tags(
    event_id: int,
    req: BibTagsRequest,
    db: Session = Depends(get_db),
) -> BibTagsResult:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    added = 0
    for entry in req.tags:
        exists = (
            db.query(PhotoTag)
            .filter(
                PhotoTag.photo_id == entry.photo_id,
                PhotoTag.tag_type == "bib",
                PhotoTag.value == entry.bib,
            )
            .first()
        )
        if not exists:
            db.add(
                PhotoTag(
                    photo_id=entry.photo_id,
                    tag_type="bib",
                    value=entry.bib,
                    confidence=entry.confidence,
                )
            )
            added += 1

    db.commit()
    return BibTagsResult(added=added)
