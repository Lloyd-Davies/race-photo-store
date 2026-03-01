from pathlib import Path
from datetime import datetime, timedelta, timezone
import hmac
import re
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from app.admin_session import create_admin_session_tokens, verify_admin_session_token
from app.deps import get_db, require_admin
from app.event_access import hash_event_password
from app.rate_limit import enforce_rate_limit
from app.schemas import (
    AdminLoginRequest,
    AdminStatsOut,
    AdminRefreshRequest,
    AdminOrderListOut,
    AdminOrderOut,
    AdminResetDeliveryRequest,
    AdminSessionOut,
    BibTagsRequest,
    BibTagsResult,
    CreateEventRequest,
    DeleteEventResult,
    PhotoIdsOut,
    PhotoUploadResult,
    EventCreatedOut,
    IngestResult,
    UpdateEventRequest,
)
from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.models import Cart, Delivery, Event, EventStatus, Order, OrderItem, OrderStatus, Photo, PhotoState, PhotoTag

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _parse_exif_offset(raw_offset: str | None) -> timezone | None:
    if not raw_offset:
        return None
    try:
        raw = raw_offset.strip()
        if len(raw) != 6 or raw[0] not in {"+", "-"} or raw[3] != ":":
            return None
        sign = 1 if raw[0] == "+" else -1
        hours = int(raw[1:3])
        minutes = int(raw[4:6])
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    except Exception:
        return None


def _extract_captured_at(image_path: Path) -> datetime | None:
    if not image_path.exists():
        return None

    try:
        from PIL import Image
    except Exception:
        return None

    try:
        with Image.open(image_path) as img:
            exif = img.getexif()

        dt_raw = exif.get(0x9003) or exif.get(0x0132)
        if not dt_raw:
            return None

        dt_text = str(dt_raw).split(".")[0]
        captured = datetime.strptime(dt_text, "%Y:%m:%d %H:%M:%S")

        offset_raw = exif.get(0x9011) or exif.get(0x9010)
        tz = _parse_exif_offset(str(offset_raw) if offset_raw else None)
        if tz is None:
            return captured.replace(tzinfo=timezone.utc)

        return captured.replace(tzinfo=tz).astimezone(timezone.utc)
    except Exception:
        return None


def _to_admin_order_out(order: Order, item_count: int, delivery: Delivery | None) -> AdminOrderOut:
    return AdminOrderOut(
        id=order.id,
        status=order.status,
        email=order.email,
        created_at=order.created_at,
        paid_at=order.paid_at,
        item_count=item_count,
        event_slug=delivery.event_slug if delivery else None,
        download_count=delivery.download_count if delivery else None,
        max_downloads=delivery.max_downloads if delivery else None,
        expires_at=delivery.expires_at if delivery else None,
        download_url=(f"{settings.PUBLIC_BASE_URL}/d/{delivery.token}" if delivery else None),
    )


@router.post("/login", response_model=AdminSessionOut)
def admin_login(
    req: AdminLoginRequest,
    request: Request,
    x_admin_token: str | None = Header(default=None),
) -> AdminSessionOut:
    enforce_rate_limit(request, scope="admin-login", limit=20, window_seconds=60)

    provided = req.admin_token.strip() if req.admin_token else ""
    fallback = x_admin_token.strip() if x_admin_token else ""
    candidate = provided or fallback

    if not candidate or not settings.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    if not hmac.compare_digest(candidate, settings.ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    access_token, access_expires_at, refresh_token, refresh_expires_at = create_admin_session_tokens()
    return AdminSessionOut(
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expires_at,
    )


@router.post("/refresh", response_model=AdminSessionOut)
def refresh_admin_session(req: AdminRefreshRequest, request: Request) -> AdminSessionOut:
    enforce_rate_limit(request, scope="admin-refresh", limit=40, window_seconds=60)

    if not verify_admin_session_token(req.refresh_token, token_type="refresh"):
        raise HTTPException(status_code=401, detail="Invalid admin refresh token")

    access_token, access_expires_at, refresh_token, refresh_expires_at = create_admin_session_tokens()
    return AdminSessionOut(
        access_token=access_token,
        access_expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expires_at,
    )


@router.get("/session", dependencies=[Depends(require_admin)])
def verify_admin_session() -> dict:
    return {"ok": True}


@router.get("/events", response_model=list[EventCreatedOut], dependencies=[Depends(require_admin)])
def list_admin_events(db: Session = Depends(get_db)) -> list[EventCreatedOut]:
    """Return all events regardless of status (admin view), newest first by ID."""
    events = db.query(Event).order_by(Event.id.desc()).all()
    return [EventCreatedOut(id=e.id, slug=e.slug) for e in events]


@router.post("/events", response_model=EventCreatedOut, dependencies=[Depends(require_admin)])
def create_event(req: CreateEventRequest, db: Session = Depends(get_db)) -> EventCreatedOut:
    if db.query(Event).filter(Event.slug == req.slug).first():
        raise HTTPException(409, f"Event slug '{req.slug}' already exists")

    access_secret = (req.access_secret or req.access_password or "").strip()
    if req.is_password_protected and not access_secret:
        raise HTTPException(400, "Protected events require an access secret")

    event = Event(
        slug=req.slug,
        name=req.name,
        date=req.date,
        location=req.location,
        is_password_protected=req.is_password_protected,
        access_password_hash=(hash_event_password(access_secret) if req.is_password_protected and access_secret else None),
        access_hint=(req.access_hint if req.is_password_protected else None),
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return EventCreatedOut(id=event.id, slug=event.slug)


@router.patch("/events/{event_id}", dependencies=[Depends(require_admin)])
def update_event(
    event_id: int,
    req: UpdateEventRequest,
    db: Session = Depends(get_db),
) -> EventCreatedOut:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    payload = req.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "No fields supplied")

    access_secret = payload.pop("access_secret", None)
    access_password = payload.pop("access_password", None)
    clear_access_secret = payload.pop("clear_access_secret", False)
    clear_access_password = payload.pop("clear_access_password", False)

    for field, value in payload.items():
        setattr(event, field, value)

    if clear_access_secret or clear_access_password:
        event.access_password_hash = None

    supplied_secret = access_secret if access_secret is not None else access_password
    if supplied_secret is not None:
        supplied_secret = supplied_secret.strip()
        if not supplied_secret:
            raise HTTPException(400, "access_secret must not be empty")
        event.access_password_hash = hash_event_password(supplied_secret)

    if event.is_password_protected and not event.access_password_hash:
        raise HTTPException(400, "Protected events require an access secret")

    if not event.is_password_protected:
        event.access_password_hash = None
        event.access_hint = None

    db.commit()
    db.refresh(event)
    return EventCreatedOut(id=event.id, slug=event.slug)


@router.get("/stats", response_model=AdminStatsOut, dependencies=[Depends(require_admin)])
def get_admin_stats(db: Session = Depends(get_db)) -> AdminStatsOut:
    return AdminStatsOut(
        total_events=db.query(Event).count(),
        total_photos=db.query(Photo).count(),
        total_orders=db.query(Order).count(),
        total_deliveries=db.query(Delivery).count(),
        pending_orders=db.query(Order).filter(Order.status == OrderStatus.PENDING).count(),
        failed_orders=db.query(Order).filter(Order.status == OrderStatus.FAILED).count(),
        active_events=db.query(Event).filter(Event.status == EventStatus.ACTIVE).count(),
    )


@router.get(
    "/events/{event_id}/photo_ids",
    response_model=PhotoIdsOut,
    dependencies=[Depends(require_admin)],
)
def get_photo_ids(event_id: int, db: Session = Depends(get_db)) -> PhotoIdsOut:
    """Return all photo_id stems already stored for this event.

    Used by the preprocessor deploy worker to skip photos already uploaded.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    ids = [row[0] for row in db.query(Photo.id).filter(Photo.event_id == event_id).all()]
    return PhotoIdsOut(photo_ids=ids)


@router.delete(
    "/events/{event_id}",
    response_model=DeleteEventResult,
    dependencies=[Depends(require_admin)],
)
def delete_event(
    event_id: int,
    delete_files: bool = Query(default=False),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> DeleteEventResult:
    """Delete an event and all associated DB rows.

    Guards against events that have PAID orders unless force=True.
    Set delete_files=True to also remove proofs/ and originals/ from disk.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    slug = event.slug

    # Subquery for all photo IDs in this event — keeps filtering in the DB,
    # avoiding materialising a potentially huge list in Python memory.
    photo_subq = db.query(Photo.id).filter(Photo.event_id == event_id).scalar_subquery()

    # Count paid orders that reference photos in this event
    orders_affected = (
        db.query(Order)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(
            OrderItem.photo_id.in_(photo_subq),
            Order.status == OrderStatus.PAID,
        )
        .distinct()
        .count()
    )

    if orders_affected > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "orders_affected": orders_affected,
                "message": (
                    f"{orders_affected} paid order(s) reference photos in this event. "
                    "Set force=true to delete anyway."
                ),
            },
        )

    # Delete in FK-safe order, using the same subquery to avoid a Python-side list
    tags_deleted = (
        db.query(PhotoTag)
        .filter(PhotoTag.photo_id.in_(photo_subq))
        .delete(synchronize_session="fetch")
    )
    db.query(OrderItem).filter(OrderItem.photo_id.in_(photo_subq)).delete(synchronize_session="fetch")

    db.query(Delivery).filter(Delivery.event_slug == slug).delete(synchronize_session="fetch")
    db.query(Cart).filter(Cart.event_id == event_id).delete(synchronize_session="fetch")

    photos_deleted = db.query(Photo).filter(Photo.event_id == event_id).delete(synchronize_session="fetch")
    db.delete(event)
    db.commit()

    # Optionally remove files from disk
    # Catch filesystem errors so a stale/unwritable directory doesn't mask
    # the fact that the DB deletion already succeeded.
    files_deleted = False
    if delete_files:
        import shutil
        storage_root = Path(settings.STORAGE_ROOT)
        try:
            for kind in ("proofs", "originals"):
                target = storage_root / kind / slug
                if target.exists():
                    shutil.rmtree(target)
            files_deleted = True
        except OSError:
            files_deleted = False

    return DeleteEventResult(
        slug=slug,
        photos_deleted=photos_deleted,
        tags_deleted=tags_deleted,
        orders_affected=orders_affected,
        files_deleted=files_deleted,
    )


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
        captured_at = _extract_captured_at(original)
        if captured_at is None:
            captured_at = _extract_captured_at(filepath)

        db.add(
            Photo(
                id=photo_id,
                event_id=event_id,
                captured_at=captured_at,
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
    if req.replace:
        db.query(PhotoTag).filter(
            PhotoTag.photo_id.in_(
                db.query(Photo.id).filter(Photo.event_id == event_id)
            ),
            PhotoTag.tag_type == "bib",
        ).delete(synchronize_session="fetch")

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


@router.post(
    "/events/{event_id}/photos",
    response_model=PhotoUploadResult,
    dependencies=[Depends(require_admin)],
)
def upload_photo(
    event_id: int,
    photo_id: str = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PhotoUploadResult:
    """Upload a single image (original or proof) for an event.

    Saves to {STORAGE_ROOT}/{kind}s/{slug}/{photo_id}.jpg and creates or
    updates the Photo DB record. kind must be 'original' or 'proof'.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    if kind not in ("original", "proof"):
        raise HTTPException(400, "kind must be 'original' or 'proof'")

    # Validate photo_id to prevent path traversal attacks
    if not re.match(r'^[A-Za-z0-9_-]+$', photo_id):
        raise HTTPException(400, "photo_id must contain only alphanumeric characters, hyphens, or underscores")

    # Cross-event collision check: reject before touching the filesystem so no
    # orphaned file is written when the photo_id belongs to a different event.
    existing = db.query(Photo).filter(Photo.id == photo_id).first()
    if existing is not None and existing.event_id != event_id:
        raise HTTPException(
            status_code=409,
            detail=f"photo_id '{photo_id}' already belongs to a different event.",
        )
    created = existing is None

    storage_root = Path(settings.STORAGE_ROOT)
    dest_dir = storage_root / f"{kind}s" / event.slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{photo_id}.jpg"

    # Stream to a temporary file first, then atomically rename into place.
    # This prevents a partial JPEG being left at the canonical path if the
    # client disconnects or the process crashes mid-upload.
    size_bytes = 0
    tmp = tempfile.NamedTemporaryFile(dir=dest_dir, suffix=".tmp", delete=False)
    try:
        with tmp:
            while True:
                chunk = file.file.read(262144)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > settings.MAX_PHOTO_UPLOAD_BYTES:
                    raise HTTPException(
                        413,
                        f"Uploaded file exceeds max size ({settings.MAX_PHOTO_UPLOAD_BYTES} bytes)",
                    )
                tmp.write(chunk)
        Path(tmp.name).replace(dest_path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise

    if kind == "proof":
        if existing is None:
            db.add(Photo(
                id=photo_id,
                event_id=event_id,
                proof_path=f"proofs/{event.slug}/{photo_id}.jpg",
                original_path=f"originals/{event.slug}/{photo_id}.jpg",
                state=PhotoState.MISSING,
            ))
        else:
            existing.proof_path = f"proofs/{event.slug}/{photo_id}.jpg"
    else:  # original
        captured_at = _extract_captured_at(dest_path)
        if existing is None:
            db.add(Photo(
                id=photo_id,
                event_id=event_id,
                captured_at=captured_at,
                proof_path=f"proofs/{event.slug}/{photo_id}.jpg",
                original_path=f"originals/{event.slug}/{photo_id}.jpg",
                state=PhotoState.READY,
            ))
        else:
            existing.original_path = f"originals/{event.slug}/{photo_id}.jpg"
            existing.state = PhotoState.READY
            if captured_at:
                existing.captured_at = captured_at

    db.commit()
    return PhotoUploadResult(
        photo_id=photo_id,
        kind=kind,
        size_bytes=size_bytes,
        created=created,
    )


@router.get("/orders", response_model=AdminOrderListOut, dependencies=[Depends(require_admin)])
def list_orders(
    status: OrderStatus | None = None,
    q: str | None = Query(default=None, description="Search by order id/email/event slug/token"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> AdminOrderListOut:
    item_count_subq = (
        db.query(OrderItem.order_id, func.count(OrderItem.id).label("item_count"))
        .group_by(OrderItem.order_id)
        .subquery()
    )

    query = (
        db.query(Order, Delivery, item_count_subq.c.item_count)
        .outerjoin(Delivery, Delivery.order_id == Order.id)
        .outerjoin(item_count_subq, item_count_subq.c.order_id == Order.id)
        .options(joinedload(Order.items))
        .order_by(Order.id.desc())
    )

    if status:
        query = query.filter(Order.status == status)

    rows = query.limit(limit).all()

    if q:
        needle = q.strip().lower()
        filtered_rows = []
        for order, delivery, item_count in rows:
            haystack = [
                str(order.id),
                (order.email or "").lower(),
                (delivery.event_slug.lower() if delivery else ""),
                (delivery.token.lower() if delivery else ""),
            ]
            if any(needle in h for h in haystack):
                filtered_rows.append((order, delivery, item_count))
        rows = filtered_rows

    result: list[AdminOrderOut] = []
    for order, delivery, item_count in rows:
        result.append(_to_admin_order_out(order, int(item_count or 0), delivery))

    return AdminOrderListOut(orders=result)


@router.post(
    "/orders/{order_id}/reset-delivery",
    response_model=AdminOrderOut,
    dependencies=[Depends(require_admin)],
)
def reset_delivery(
    order_id: int,
    req: AdminResetDeliveryRequest,
    db: Session = Depends(get_db),
) -> AdminOrderOut:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
    if not delivery:
        raise HTTPException(409, "Order does not have a delivery yet")

    if req.days_valid < 1 or req.days_valid > 365:
        raise HTTPException(400, "days_valid must be between 1 and 365")

    if req.rotate_token:
        delivery.token = str(uuid.uuid4())

    delivery.download_count = 0
    delivery.expires_at = datetime.now(timezone.utc) + timedelta(days=req.days_valid)
    if req.max_downloads is not None:
        if req.max_downloads < 1 or req.max_downloads > 100:
            raise HTTPException(400, "max_downloads must be between 1 and 100")
        delivery.max_downloads = req.max_downloads

    db.commit()
    db.refresh(delivery)

    item_count = db.query(OrderItem).filter(OrderItem.order_id == order_id).count()

    return _to_admin_order_out(order, item_count, delivery)


@router.post(
    "/orders/{order_id}/expire-delivery",
    response_model=AdminOrderOut,
    dependencies=[Depends(require_admin)],
)
def expire_delivery(order_id: int, db: Session = Depends(get_db)) -> AdminOrderOut:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
    if not delivery:
        raise HTTPException(409, "Order does not have a delivery yet")

    delivery.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    order.status = OrderStatus.EXPIRED
    db.commit()
    db.refresh(delivery)
    db.refresh(order)

    item_count = db.query(OrderItem).filter(OrderItem.order_id == order_id).count()
    return _to_admin_order_out(order, item_count, delivery)


@router.post(
    "/orders/{order_id}/rebuild-zip",
    response_model=AdminOrderOut,
    dependencies=[Depends(require_admin)],
)
def rebuild_order_zip(order_id: int, db: Session = Depends(get_db)) -> AdminOrderOut:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    if order.status == OrderStatus.PENDING:
        raise HTTPException(409, "Order is not paid yet")

    if order.status == OrderStatus.BUILDING:
        raise HTTPException(409, "Order ZIP is already building")

    delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
    if delivery:
        zip_abs_path = Path(settings.STORAGE_ROOT) / delivery.zip_path
        if zip_abs_path.exists():
            zip_abs_path.unlink()
        db.delete(delivery)
        db.flush()

    order.status = OrderStatus.PAID
    db.commit()

    celery_app.send_task("tasks.build_zip.build_zip", args=[order.id])

    db.refresh(order)
    item_count = db.query(OrderItem).filter(OrderItem.order_id == order_id).count()
    return _to_admin_order_out(order, item_count, None)
