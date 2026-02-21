from pathlib import Path
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import func

from app.deps import get_db, require_admin
from app.schemas import (
    AdminOrderListOut,
    AdminOrderOut,
    AdminResetDeliveryRequest,
    BibTagsRequest,
    BibTagsResult,
    CreateEventRequest,
    EventCreatedOut,
    IngestResult,
)
from photostore.config import settings
from photostore.models import Delivery, Event, Order, OrderItem, OrderStatus, Photo, PhotoState, PhotoTag

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
        result.append(
            AdminOrderOut(
                id=order.id,
                status=order.status,
                email=order.email,
                created_at=order.created_at,
                paid_at=order.paid_at,
                item_count=int(item_count or 0),
                event_slug=delivery.event_slug if delivery else None,
                download_count=delivery.download_count if delivery else None,
                max_downloads=delivery.max_downloads if delivery else None,
                expires_at=delivery.expires_at if delivery else None,
                download_url=(f"{settings.PUBLIC_BASE_URL}/d/{delivery.token}" if delivery else None),
            )
        )

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

    return AdminOrderOut(
        id=order.id,
        status=order.status,
        email=order.email,
        created_at=order.created_at,
        paid_at=order.paid_at,
        item_count=item_count,
        event_slug=delivery.event_slug,
        download_count=delivery.download_count,
        max_downloads=delivery.max_downloads,
        expires_at=delivery.expires_at,
        download_url=f"{settings.PUBLIC_BASE_URL}/d/{delivery.token}",
    )
