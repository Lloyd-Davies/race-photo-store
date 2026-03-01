import math
from datetime import datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import cast, Time

from app.deps import get_db
from app.event_access import create_event_access_token, verify_event_access_token, verify_event_password
from app.schemas import EventOut, EventUnlockOut, EventUnlockRequest, PhotoListOut, PhotoOut
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
    start_time: Optional[str] = Query(None, description="Filter captured_at >= HH:MM"),
    end_time: Optional[str] = Query(None, description="Filter captured_at <= HH:MM"),
    page_size: int = Query(50, ge=1, le=200),
    x_event_access: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> PhotoListOut:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return PhotoListOut(photos=[], total=0, page=page, pages=1)

    if event.is_password_protected and not verify_event_access_token(x_event_access, event_id):
        raise HTTPException(401, "Event is locked. Unlock required.")

    q = db.query(Photo).filter(Photo.event_id == event_id)

    if bib is not None:
        q = q.join(PhotoTag).filter(
            PhotoTag.tag_type == "bib",
            PhotoTag.value == bib,
        )

    start_time_obj: time | None = None
    end_time_obj: time | None = None
    try:
        if start_time:
            start_time_obj = datetime.strptime(start_time, "%H:%M").time()
        if end_time:
            end_time_obj = datetime.strptime(end_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(400, "Invalid time format. Use HH:MM")

    if start_time_obj or end_time_obj:
        q = q.filter(Photo.captured_at.is_not(None))
        captured_time = cast(Photo.captured_at, Time)
        if start_time_obj:
            q = q.filter(captured_time >= start_time_obj)
        if end_time_obj:
            q = q.filter(captured_time <= end_time_obj)

    total = q.count()
    photos = q.order_by(Photo.captured_at.asc().nullslast(), Photo.id.asc()).offset((page - 1) * page_size).limit(page_size).all()

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


@router.post("/events/{event_id}/unlock", response_model=EventUnlockOut)
def unlock_event(
    event_id: int,
    req: EventUnlockRequest,
    db: Session = Depends(get_db),
) -> EventUnlockOut:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    if not event.is_password_protected:
        raise HTTPException(400, "Event is not password protected")

    if not verify_event_password(req.password, event.access_password_hash):
        raise HTTPException(401, "Invalid event password")

    token, expires_at = create_event_access_token(event.id)
    return EventUnlockOut(access_token=token, expires_at=expires_at)
