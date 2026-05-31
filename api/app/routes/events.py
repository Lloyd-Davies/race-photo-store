import math
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import cast, Time, func, or_

from app.deps import get_db
from app.event_access import create_event_access_token, verify_event_access_token, verify_event_password
from app.rate_limit import enforce_rate_limit
from app.schemas import EventOut, EventUnlockOut, EventUnlockRequest, PhotoListOut, PhotoOut
from photostore.config import settings
from photostore.models import Event, EventStatus, Photo, PhotoTag
from photostore.pricing import effective_photo_price_pence, get_app_settings

router = APIRouter(prefix="/api", tags=["events"])
public_router = APIRouter(tags=["events"])

PUBLIC_PROOF_CACHE_CONTROL = "public, max-age=2592000, immutable"
LEGACY_PROOF_CACHE_CONTROL = "no-store"


def _is_event_publicly_visible(event: Event, now: datetime | None = None) -> bool:
    check_time = now or datetime.now(timezone.utc)
    if event.status != EventStatus.ACTIVE:
        return False
    if event.public_until and event.public_until < check_time:
        return False
    if event.archive_after and event.archive_after <= check_time:
        return False
    return True


def _event_out(event: Event, app_settings) -> EventOut:
    return EventOut(
        id=event.id,
        slug=event.slug,
        name=event.name,
        date=event.date,
        location=event.location,
        status=event.status,
        is_password_protected=event.is_password_protected,
        access_hint=event.access_hint,
        public_until=event.public_until,
        archive_after=event.archive_after,
        photo_price_pence=event.photo_price_pence,
        effective_photo_price_pence=effective_photo_price_pence(event, app_settings),
        currency=app_settings.currency,
    )


def _resolve_event_ref(event_ref: str, db: Session) -> Event | None:
    event = db.query(Event).filter(Event.slug == event_ref).first()
    if event:
        return event
    if event_ref.isdigit():
        return db.query(Event).filter(Event.id == int(event_ref)).first()
    return None


def _resolve_visible_event_ref(event_ref: str, db: Session) -> Event | None:
    event = _resolve_event_ref(event_ref, db)
    if not event or not _is_event_publicly_visible(event):
        return None
    return event


def _proof_accel_path(photo: Photo) -> tuple[Path, str]:
    proof_abs = (Path(settings.STORAGE_ROOT) / photo.proof_path).resolve()
    proofs_root = (Path(settings.STORAGE_ROOT) / "proofs").resolve()

    try:
        proof_rel = proof_abs.relative_to(proofs_root)
    except ValueError:
        raise HTTPException(500, "Invalid proof image path")

    if not proof_abs.exists():
        raise HTTPException(404, "Proof image not found")

    return proof_abs, f"/_internal_proofs/{proof_rel.as_posix()}"


def _photo_proof_response(photo: Photo, cache_control: str) -> Response:
    _, accel_path = _proof_accel_path(photo)
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": accel_path,
            "Content-Type": "image/jpeg",
            "Cache-Control": cache_control,
        },
    )


@router.get("/events", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)) -> list[EventOut]:
    now = datetime.now(timezone.utc)
    app_settings = get_app_settings(db)
    events = (
        db.query(Event)
        .filter(Event.status == EventStatus.ACTIVE)
        .filter(or_(Event.public_until.is_(None), Event.public_until >= now))
        .filter(or_(Event.archive_after.is_(None), Event.archive_after > now))
        .order_by(Event.date.desc())
        .all()
    )
    return [_event_out(event, app_settings) for event in events]


@router.get("/events/{event_ref}", response_model=EventOut)
def get_event(event_ref: str, db: Session = Depends(get_db)) -> EventOut:
    event = _resolve_visible_event_ref(event_ref, db)
    if not event:
        raise HTTPException(404, "Event not found")
    return _event_out(event, get_app_settings(db))


@router.get("/events/{event_ref}/photos", response_model=PhotoListOut)
def list_photos(
    event_ref: str,
    page: int = Query(1, ge=1),
    bib: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None, description="Filter captured_at >= HH:MM"),
    end_time: Optional[str] = Query(None, description="Filter captured_at <= HH:MM"),
    page_size: int = Query(50, ge=1, le=200),
    x_event_access: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> PhotoListOut:
    event = _resolve_visible_event_ref(event_ref, db)
    if not event:
        return PhotoListOut(photos=[], total=0, page=page, pages=1)

    if event.is_password_protected and not verify_event_access_token(x_event_access, event.id):
        raise HTTPException(401, "Event is locked. Unlock required.")

    q = db.query(Photo).filter(Photo.event_id == event.id)

    if bib is not None:
        bib_value = bib.strip()
        tag_value = func.trim(PhotoTag.value)
        q = q.join(PhotoTag).filter(PhotoTag.tag_type == "bib")
        if bib_value.isdigit():
            normalized_digits = bib_value.lstrip("0") or "0"
            q = q.filter(
                or_(
                    tag_value == bib_value,
                    func.ltrim(tag_value, "0") == normalized_digits,
                )
            )
        else:
            q = q.filter(tag_value == bib_value)
        q = q.distinct()

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
                proof_url=(
                    f"/api/events/{event.slug}/photos/{p.id}/proof?access_token={x_event_access}"
                    if event.is_password_protected and x_event_access
                    else f"/proofs/{event.slug}/{p.id}.jpg"
                ),
                captured_at=p.captured_at,
            )
            for p in photos
        ],
        total=total,
        page=page,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.post("/events/{event_ref}/unlock", response_model=EventUnlockOut)
def unlock_event(
    event_ref: str,
    req: EventUnlockRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> EventUnlockOut:
    event = _resolve_visible_event_ref(event_ref, db)
    if not event:
        raise HTTPException(404, "Event not found")

    enforce_rate_limit(request, scope="event-unlock", limit=15, window_seconds=60, suffix=str(event.id))

    if not event.is_password_protected:
        raise HTTPException(400, "Event is not password protected")

    access_secret = (req.secret or req.password or "").strip()
    if not access_secret:
        raise HTTPException(400, "Event secret is required")

    if not verify_event_password(access_secret, event.access_password_hash):
        raise HTTPException(401, "Invalid event secret")

    token, expires_at = create_event_access_token(event.id)
    return EventUnlockOut(access_token=token, expires_at=expires_at)


@router.get("/events/{event_ref}/photos/{photo_id}/proof")
def get_event_proof(
    event_ref: str,
    photo_id: str,
    x_event_access: Optional[str] = Header(None),
    access_token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    event = _resolve_visible_event_ref(event_ref, db)
    if not event:
        raise HTTPException(404, "Event not found")

    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.event_id == event.id)
        .first()
    )
    if not photo:
        raise HTTPException(404, "Photo not found")

    provided_access = x_event_access or access_token
    if event.is_password_protected and not verify_event_access_token(provided_access, event.id):
        raise HTTPException(401, "Event is locked. Unlock required.")

    return _photo_proof_response(photo, LEGACY_PROOF_CACHE_CONTROL)


@public_router.get("/proofs/{event_ref}/{photo_id}.jpg")
def get_public_proof(
    event_ref: str,
    photo_id: str,
    db: Session = Depends(get_db),
) -> Response:
    event = _resolve_visible_event_ref(event_ref, db)
    if (
        not event
        or event.is_password_protected
    ):
        raise HTTPException(404, "Proof image not found")

    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.event_id == event.id)
        .first()
    )
    if not photo:
        raise HTTPException(404, "Proof image not found")

    return _photo_proof_response(photo, PUBLIC_PROOF_CACHE_CONTROL)
