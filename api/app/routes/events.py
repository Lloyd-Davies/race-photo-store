import math
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas import EventOut, PhotoListOut, PhotoOut
from photostore.models import Event, Photo, PhotoTag

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)) -> list[Event]:
    return db.query(Event).order_by(Event.date.desc()).all()


@router.get("/events/{event_id}/photos", response_model=PhotoListOut)
def list_photos(
    event_id: int,
    page: int = Query(1, ge=1),
    bib: Optional[str] = Query(None),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> PhotoListOut:
    q = db.query(Photo).filter(Photo.event_id == event_id)

    if bib is not None:
        q = q.join(PhotoTag).filter(
            PhotoTag.tag_type == "bib",
            PhotoTag.value == bib,
        )

    total = q.count()
    photos = q.order_by(Photo.captured_at.asc()).offset((page - 1) * page_size).limit(page_size).all()

    return PhotoListOut(
        photos=[
            PhotoOut(
                photo_id=p.id,
                proof_url=f"/{p.proof_path}",
                captured_at=p.captured_at,
            )
            for p in photos
        ],
        total=total,
        page=page,
        pages=max(1, math.ceil(total / page_size)),
    )
