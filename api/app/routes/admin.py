from pathlib import Path
from collections import defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hmac
from io import StringIO
import os
import re
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import String, asc, cast, desc, func, or_
import stripe

from app.communication_queue import enqueue_communication_after_commit
from app.admin_session import create_admin_session_tokens, verify_admin_session_token
from app.deps import get_db, require_admin
from app.event_access import hash_event_password
from app.rate_limit import enforce_rate_limit
from app.schemas import (
    AdminCheckoutSettingsUpdate,
    AdminEventOut,
    AdminLoginRequest,
    AdminEmailConfigOut,
    AdminEmailTestRequest,
    AdminEmailTestOut,
    AdminActivityOut,
    AdminBreakdownMetric,
    AdminCustomerMetric,
    AdminEventMetric,
    AdminMetricsOut,
    AdminMetricsTotals,
    AdminMoneyMetric,
    AdminOrderDetailOut,
    AdminOrderItemOut,
    AdminSettingsOut,
    AdminSendEmailRequest,
    AdminStatsOut,
    AdminRefreshRequest,
    AdminOrderListOut,
    AdminOrderOut,
    AdminOperationalAlert,
    AdminOrderTimelineOut,
    AdminPhotoMetric,
    AdminResetDeliveryRequest,
    AdminSessionOut,
    AdminStripeSyncOut,
    AdminStripeWebhookHealth,
    AdminTrendPoint,
    BibTagsRequest,
    BibTagsResult,
    CommunicationOut,
    CreateEventRequest,
    DeleteEventResult,
    PhotoIdsOut,
    PhotoUploadStatusesOut,
    PhotoUploadStatusOut,
    PhotoUploadResult,
    EventCreatedOut,
    IngestResult,
    UpdateEventRequest,
)
from photostore.celery_app import celery_app
from photostore.config import settings
from photostore.delivery import ensure_delivery_for_order
from photostore.email_provider import EmailMessage, ProviderError, get_provider
from photostore.models import (
    Cart, Communication, CommunicationKind, CommunicationStatus,
    Delivery, DeliveryZipStatus, Event, EventStatus, Order, OrderItem, OrderStatus,
    OrderActivity, Photo, PhotoState, PhotoTag, StripeEvent,
)
from photostore.pricing import effective_photo_price_pence, get_app_settings, normalize_currency
from photostore.storage import get_zip_storage_backend, get_zip_storage_backend_name
from app.fulfillment import mark_order_ready
from app.order_activity import record_order_activity
from app.stripe_event_store import store_stripe_event

router = APIRouter(prefix="/api/admin", tags=["admin"])

COVER_MAX_DIMENSION = 1800
stripe.api_key = settings.STRIPE_SECRET_KEY


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

        try:
            exif_ifd = exif.get_ifd(0x8769) or {}
        except Exception:
            exif_ifd = {}

        nested_original_offsets = (
            exif_ifd.get(0x9011),
            exif_ifd.get(0x9010),
            exif_ifd.get(0x9012),
        )
        nested_digitized_offsets = (
            exif_ifd.get(0x9012),
            exif_ifd.get(0x9010),
            exif_ifd.get(0x9011),
        )
        flat_original_offsets = (exif.get(0x9011), exif.get(0x9010), exif.get(0x9012))
        flat_digitized_offsets = (exif.get(0x9012), exif.get(0x9010), exif.get(0x9011))

        capture_candidates = (
            (
                exif_ifd.get(0x9003),
                nested_original_offsets + flat_original_offsets,
            ),
            (
                exif_ifd.get(0x9004),
                nested_digitized_offsets + flat_digitized_offsets,
            ),
            (
                exif.get(0x9003),
                nested_original_offsets + flat_original_offsets,
            ),
            (
                exif.get(0x9004),
                nested_digitized_offsets + flat_digitized_offsets,
            ),
            (
                exif.get(0x0132),
                (exif_ifd.get(0x9010),) + nested_original_offsets + flat_original_offsets,
            ),
        )
        dt_raw, offset_raw = next(
            (
                (dt_value, next((offset for offset in offset_values if offset), None))
                for dt_value, offset_values in capture_candidates
                if dt_value
            ),
            (None, None),
        )
        if not dt_raw:
            return None

        dt_text = str(dt_raw).split(".")[0]
        captured = datetime.strptime(dt_text, "%Y:%m:%d %H:%M:%S")

        tz = _parse_exif_offset(str(offset_raw) if offset_raw else None)
        if tz is None:
            return captured.replace(tzinfo=timezone.utc)

        return captured.replace(tzinfo=tz).astimezone(timezone.utc)
    except Exception:
        return None


def _order_subtotal_pence(order: Order) -> int:
    return sum(max(0, item.unit_price_pence - item.discount_applied_pence) for item in order.items)


def _event_cover_url(event: Event) -> str | None:
    if not event.cover_path:
        return None

    version = ""
    if event.cover_updated_at:
        updated_at = event.cover_updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        version = f"?v={int(updated_at.timestamp())}"
    return f"/api/events/{event.slug}/cover{version}"


def _cover_destination(event: Event) -> tuple[Path, str]:
    rel_path = f"covers/{event.slug}/cover.jpg"
    return Path(settings.STORAGE_ROOT) / rel_path, rel_path


def _delete_cover_file(event: Event) -> None:
    if not event.cover_path:
        return

    storage_root = Path(settings.STORAGE_ROOT).resolve()
    cover_abs = (storage_root / event.cover_path).resolve()
    covers_root = (storage_root / "covers").resolve()
    try:
        cover_abs.relative_to(covers_root)
    except ValueError:
        return

    cover_abs.unlink(missing_ok=True)
    try:
        cover_abs.parent.rmdir()
    except OSError:
        pass


def _process_cover_upload(event: Event, file: UploadFile) -> tuple[str, int]:
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except Exception:
        raise HTTPException(500, "Image processing is not available")

    dest_path, rel_path = _cover_destination(event)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    size_bytes = 0
    upload_tmp = tempfile.NamedTemporaryFile(dir=dest_path.parent, suffix=".upload", delete=False)
    output_tmp = tempfile.NamedTemporaryFile(dir=dest_path.parent, suffix=".jpg.tmp", delete=False)
    upload_tmp_path = Path(upload_tmp.name)
    output_tmp_path = Path(output_tmp.name)
    output_tmp.close()

    try:
        with upload_tmp:
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
                upload_tmp.write(chunk)

        try:
            with Image.open(upload_tmp_path) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")
                try:
                    resample = Image.Resampling.LANCZOS
                except AttributeError:
                    resample = Image.LANCZOS
                img.thumbnail((COVER_MAX_DIMENSION, COVER_MAX_DIMENSION), resample)
                img.save(output_tmp_path, format="JPEG", quality=85, optimize=True)
        except (UnidentifiedImageError, OSError, ValueError):
            raise HTTPException(400, "Cover must be a valid image file")

        output_tmp_path.replace(dest_path)
        os.chmod(dest_path, 0o644)
        return rel_path, size_bytes
    except Exception:
        output_tmp_path.unlink(missing_ok=True)
        raise
    finally:
        upload_tmp_path.unlink(missing_ok=True)


def _to_admin_order_out(order: Order, item_count: int, delivery: Delivery | None) -> AdminOrderOut:
    return AdminOrderOut(
        id=order.id,
        status=order.status,
        email=order.email,
        created_at=order.created_at,
        paid_at=order.paid_at,
        item_count=item_count,
        subtotal_pence=_order_subtotal_pence(order),
        currency=order.currency or "GBP",
        event_slug=delivery.event_slug if delivery else None,
        download_count=delivery.download_count if delivery else None,
        max_downloads=delivery.max_downloads if delivery else None,
        expires_at=delivery.expires_at if delivery else None,
        download_url=(
            f"{settings.PUBLIC_BASE_URL}/d/{delivery.token}"
            if delivery and delivery.zip_status == DeliveryZipStatus.READY
            else None
        ),
        zip_status=delivery.zip_status if delivery else None,
        zip_expires_at=delivery.zip_expires_at if delivery else None,
        zip_error=delivery.zip_error if delivery else None,
    )


def _line_total_pence(item: OrderItem) -> int:
    return max(0, item.unit_price_pence - item.discount_applied_pence)


def _order_item_stats_subquery(db: Session):
    return (
        db.query(
            OrderItem.order_id,
            func.count(OrderItem.id).label("item_count"),
            func.coalesce(
                func.sum(func.greatest(0, OrderItem.unit_price_pence - OrderItem.discount_applied_pence)),
                0,
            ).label("subtotal_pence"),
        )
        .group_by(OrderItem.order_id)
        .subquery()
    )


def _event_order_ids(db: Session, event_id: int):
    return (
        db.query(OrderItem.order_id)
        .join(Photo, Photo.id == OrderItem.photo_id)
        .filter(Photo.event_id == event_id)
    )


def _admin_order_query(
    db: Session,
    *,
    status: OrderStatus | None = None,
    zip_status: DeliveryZipStatus | None = None,
    event_id: int | None = None,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    paid_from: datetime | None = None,
    paid_to: datetime | None = None,
):
    item_stats = _order_item_stats_subquery(db)
    query = (
        db.query(Order, Delivery, item_stats.c.item_count, item_stats.c.subtotal_pence)
        .outerjoin(Delivery, Delivery.order_id == Order.id)
        .outerjoin(item_stats, item_stats.c.order_id == Order.id)
        .options(joinedload(Order.items))
    )

    if status:
        query = query.filter(Order.status == status)
    if zip_status:
        query = query.filter(Delivery.zip_status == zip_status)
    if event_id is not None:
        query = query.filter(Order.id.in_(_event_order_ids(db, event_id)))
    if created_from:
        query = query.filter(Order.created_at >= created_from)
    if created_to:
        query = query.filter(Order.created_at <= created_to)
    if paid_from:
        query = query.filter(Order.paid_at >= paid_from)
    if paid_to:
        query = query.filter(Order.paid_at <= paid_to)
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            or_(
                cast(Order.id, String).ilike(needle),
                Order.email.ilike(needle),
                Order.stripe_session_id.ilike(needle),
                Order.stripe_payment_intent_id.ilike(needle),
                Delivery.event_slug.ilike(needle),
                Delivery.token.ilike(needle),
            )
        )
    return query, item_stats


def _apply_order_sort(query, item_stats, sort: str, direction: str):
    sort_map = {
        "id": Order.id,
        "created_at": Order.created_at,
        "paid_at": Order.paid_at,
        "status": Order.status,
        "subtotal": item_stats.c.subtotal_pence,
        "items": item_stats.c.item_count,
    }
    sort_expr = sort_map.get(sort, Order.id)
    ordered = desc(sort_expr) if direction != "asc" else asc(sort_expr)
    return query.order_by(ordered, desc(Order.id))


def _money_groups() -> defaultdict[str, dict[str, int]]:
    return defaultdict(
        lambda: {
            "gross_sales_pence": 0,
            "paid_revenue_pence": 0,
            "pending_value_pence": 0,
            "discount_pence": 0,
            "paid_order_count": 0,
            "free_order_count": 0,
        }
    )


def _money_metric_list(groups: dict[str, dict[str, int]]) -> list[AdminMoneyMetric]:
    result: list[AdminMoneyMetric] = []
    for currency, values in sorted(groups.items()):
        paid_count = values.get("paid_order_count", 0)
        paid_revenue = values.get("paid_revenue_pence", 0)
        result.append(
            AdminMoneyMetric(
                currency=currency,
                gross_sales_pence=values.get("gross_sales_pence", 0),
                paid_revenue_pence=paid_revenue,
                pending_value_pence=values.get("pending_value_pence", 0),
                discount_pence=values.get("discount_pence", 0),
                paid_order_count=paid_count,
                free_order_count=values.get("free_order_count", 0),
                average_order_value_pence=int(paid_revenue / paid_count) if paid_count else 0,
            )
        )
    return result


def _order_currency(order: Order) -> str:
    return (order.currency or "GBP").upper()


def _range_start(range_value: str, now: datetime) -> datetime | None:
    ranges = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "365d": 365,
    }
    if range_value == "all":
        return None
    return now - timedelta(days=ranges.get(range_value, 30))


def _orders_for_metrics(
    db: Session,
    *,
    event_id: int | None,
    date_field,
    start_at: datetime | None,
    end_at: datetime,
) -> list[Order]:
    query = db.query(Order).options(
        joinedload(Order.items).joinedload(OrderItem.photo).joinedload(Photo.event),
        joinedload(Order.delivery),
    )
    if start_at is not None:
        query = query.filter(date_field >= start_at)
    query = query.filter(date_field <= end_at)
    if event_id is not None:
        query = query.filter(Order.id.in_(_event_order_ids(db, event_id)))
    return query.all()


def _activity_out(activity: OrderActivity) -> AdminActivityOut:
    return AdminActivityOut(
        id=activity.id,
        source="activity",
        action=activity.action,
        actor=activity.actor,
        message=activity.message,
        order_id=activity.order_id,
        created_at=activity.created_at,
        metadata=activity.metadata_json or {},
    )


def _communication_activity_out(comm: Communication) -> AdminActivityOut:
    return AdminActivityOut(
        id=comm.id,
        source="communication",
        action=comm.kind.value,
        actor=comm.initiated_by,
        message=comm.subject,
        status=comm.status.value,
        order_id=comm.order_id,
        created_at=comm.created_at,
        metadata={
            "recipient_email": comm.recipient_email,
            "sent_at": comm.sent_at.isoformat() if comm.sent_at else None,
            "error_message": comm.error_message,
        },
    )


def _stripe_event_activity_out(event: StripeEvent) -> AdminActivityOut:
    return AdminActivityOut(
        id=event.id,
        source="stripe",
        action=event.event_type,
        actor="stripe",
        message=f"Stripe event {event.event_type}",
        status=event.processing_status,
        order_id=event.order_id,
        created_at=event.received_at,
        metadata={
            "stripe_event_id": event.stripe_event_id,
            "stripe_session_id": event.stripe_session_id,
            "payment_intent_id": event.payment_intent_id,
            "error_message": event.error_message,
        },
    )


def _admin_activity_feed(db: Session, *, order_id: int | None = None, limit: int = 20) -> list[AdminActivityOut]:
    activities_query = db.query(OrderActivity)
    comms_query = db.query(Communication)
    stripe_query = db.query(StripeEvent)
    if order_id is not None:
        activities_query = activities_query.filter(OrderActivity.order_id == order_id)
        comms_query = comms_query.filter(Communication.order_id == order_id)
        stripe_query = stripe_query.filter(StripeEvent.order_id == order_id)

    entries = (
        [_activity_out(item) for item in activities_query.order_by(OrderActivity.created_at.desc()).limit(limit).all()]
        + [_communication_activity_out(item) for item in comms_query.order_by(Communication.created_at.desc()).limit(limit).all()]
        + [_stripe_event_activity_out(item) for item in stripe_query.order_by(StripeEvent.received_at.desc()).limit(limit).all()]
    )
    return sorted(entries, key=lambda entry: entry.created_at, reverse=True)[:limit]


def _build_operational_alerts(
    db: Session,
    *,
    event_id: int | None,
    now: datetime,
) -> list[AdminOperationalAlert]:
    def order_scope(query):
        if event_id is None:
            return query
        return query.filter(Order.id.in_(_event_order_ids(db, event_id)))

    alerts: list[AdminOperationalAlert] = []

    stuck_pending = (
        order_scope(db.query(Order.id))
        .filter(Order.status == OrderStatus.PENDING, Order.created_at < now - timedelta(hours=24))
        .order_by(Order.created_at.asc())
        .all()
    )
    if stuck_pending:
        alerts.append(
            AdminOperationalAlert(
                type="STUCK_PENDING",
                severity="warning",
                count=len(stuck_pending),
                message="Pending orders older than 24 hours may need Stripe reconciliation.",
                order_ids=[row[0] for row in stuck_pending[:10]],
            )
        )

    failed_orders = (
        order_scope(db.query(Order.id))
        .filter(Order.status == OrderStatus.FAILED)
        .order_by(Order.created_at.desc())
        .all()
    )
    if failed_orders:
        alerts.append(
            AdminOperationalAlert(
                type="FAILED_ORDERS",
                severity="critical",
                count=len(failed_orders),
                message="Orders are marked failed.",
                order_ids=[row[0] for row in failed_orders[:10]],
            )
        )

    failed_zips = (
        order_scope(db.query(Order.id).join(Delivery, Delivery.order_id == Order.id))
        .filter(Delivery.zip_status == DeliveryZipStatus.FAILED)
        .order_by(Order.created_at.desc())
        .all()
    )
    if failed_zips:
        alerts.append(
            AdminOperationalAlert(
                type="FAILED_ZIPS",
                severity="critical",
                count=len(failed_zips),
                message="ZIP builds have failed and may need rebuilding.",
                order_ids=[row[0] for row in failed_zips[:10]],
            )
        )

    expired_links = (
        order_scope(db.query(Order.id).join(Delivery, Delivery.order_id == Order.id))
        .filter(Delivery.expires_at < now)
        .order_by(Delivery.expires_at.asc())
        .all()
    )
    if expired_links:
        alerts.append(
            AdminOperationalAlert(
                type="EXPIRED_LINKS",
                severity="warning",
                count=len(expired_links),
                message="Delivery links have expired.",
                order_ids=[row[0] for row in expired_links[:10]],
            )
        )

    expiring_links = (
        order_scope(db.query(Order.id).join(Delivery, Delivery.order_id == Order.id))
        .filter(Delivery.expires_at >= now, Delivery.expires_at <= now + timedelta(hours=48))
        .order_by(Delivery.expires_at.asc())
        .all()
    )
    if expiring_links:
        alerts.append(
            AdminOperationalAlert(
                type="EXPIRING_LINKS",
                severity="info",
                count=len(expiring_links),
                message="Delivery links expire within 48 hours.",
                order_ids=[row[0] for row in expiring_links[:10]],
            )
        )

    max_downloads = (
        order_scope(db.query(Order.id).join(Delivery, Delivery.order_id == Order.id))
        .filter(Delivery.download_count >= Delivery.max_downloads)
        .order_by(Order.created_at.desc())
        .all()
    )
    if max_downloads:
        alerts.append(
            AdminOperationalAlert(
                type="MAX_DOWNLOADS",
                severity="warning",
                count=len(max_downloads),
                message="Download limits have been reached.",
                order_ids=[row[0] for row in max_downloads[:10]],
            )
        )

    failed_email_query = (
        db.query(Communication.order_id)
        .filter(Communication.status.in_([
            CommunicationStatus.FAILED,
            CommunicationStatus.BOUNCED,
            CommunicationStatus.BLOCKED,
        ]))
        .order_by(Communication.created_at.desc())
    )
    if event_id is not None:
        failed_email_query = failed_email_query.filter(Communication.order_id.in_(_event_order_ids(db, event_id)))
    failed_emails = failed_email_query.all()
    if failed_emails:
        alerts.append(
            AdminOperationalAlert(
                type="FAILED_EMAILS",
                severity="warning",
                count=len(failed_emails),
                message="Transactional emails failed, bounced, or were blocked.",
                order_ids=[row[0] for row in failed_emails[:10] if row[0] is not None],
            )
        )

    return alerts


def _stripe_session_dict(session) -> dict:
    if isinstance(session, dict):
        return session
    try:
        as_dict = dict(session)
        if as_dict:
            return as_dict
    except Exception:
        pass
    return {
        "id": getattr(session, "id", None),
        "status": getattr(session, "status", None),
        "payment_status": getattr(session, "payment_status", None),
        "payment_intent": getattr(session, "payment_intent", None),
        "customer_email": getattr(session, "customer_email", None),
    }


def _apply_stripe_session_to_order(
    order: Order,
    session: dict,
    db: Session,
    *,
    actor: str,
) -> tuple[bool, int | None]:
    payment_status = session.get("payment_status")
    status = session.get("status")
    changed = False
    communication_id = None

    if payment_status == "paid" or status == "complete":
        if order.status == OrderStatus.PENDING:
            communication_id = mark_order_ready(
                order,
                db,
                payment_intent_id=session.get("payment_intent"),
                customer_email=session.get("customer_email"),
                initiated_by=actor,
            )
            record_order_activity(
                db,
                order_id=order.id,
                action="STRIPE_SYNC_COMPLETED",
                message="Order marked ready after Stripe sync",
                actor=actor,
                metadata={"stripe_session_id": session.get("id")},
            )
            changed = True
    elif status == "expired" and order.status == OrderStatus.PENDING:
        order.status = OrderStatus.FAILED
        record_order_activity(
            db,
            order_id=order.id,
            action="STRIPE_SYNC_EXPIRED",
            message="Order marked failed after Stripe reported an expired session",
            actor=actor,
            metadata={"stripe_session_id": session.get("id")},
        )
        changed = True

    if session.get("payment_intent") and order.stripe_payment_intent_id != session.get("payment_intent"):
        order.stripe_payment_intent_id = session.get("payment_intent")
        changed = True
    if session.get("customer_email") and order.email != session.get("customer_email"):
        order.email = session.get("customer_email")
        changed = True
    return changed, communication_id


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


@router.get("/events", response_model=list[AdminEventOut], dependencies=[Depends(require_admin)])
def list_admin_events(db: Session = Depends(get_db)) -> list[AdminEventOut]:
    """Return all events regardless of public visibility, newest first by ID."""
    app_settings = get_app_settings(db)
    events = db.query(Event).order_by(Event.id.desc()).all()
    result: list[AdminEventOut] = []
    for event in events:
        photo_count = db.query(Photo).filter(Photo.event_id == event.id).count()
        order_count = (
            db.query(Order)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .join(Photo, Photo.id == OrderItem.photo_id)
            .filter(Photo.event_id == event.id)
            .distinct()
            .count()
        )
        result.append(
            AdminEventOut(
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
                cover_url=_event_cover_url(event),
                photo_count=photo_count,
                order_count=order_count,
            )
        )
    return result


@router.post("/events", response_model=EventCreatedOut, dependencies=[Depends(require_admin)])
def create_event(req: CreateEventRequest, db: Session = Depends(get_db)) -> EventCreatedOut:
    if db.query(Event).filter(Event.slug == req.slug).first():
        raise HTTPException(409, f"Event slug '{req.slug}' already exists")

    access_secret = (req.access_secret or req.access_password or "").strip()
    if req.is_password_protected and not access_secret:
        raise HTTPException(400, "Protected events require an access secret")
    if req.photo_price_pence is not None and req.photo_price_pence < 0:
        raise HTTPException(400, "photo_price_pence must be 0 or greater")

    event = Event(
        slug=req.slug,
        name=req.name,
        date=req.date,
        location=req.location,
        is_password_protected=req.is_password_protected,
        access_password_hash=(hash_event_password(access_secret) if req.is_password_protected and access_secret else None),
        access_hint=(req.access_hint if req.is_password_protected else None),
        photo_price_pence=req.photo_price_pence,
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
    clear_photo_price = payload.pop("clear_photo_price", False)

    if payload.get("photo_price_pence") is not None and payload["photo_price_pence"] < 0:
        raise HTTPException(400, "photo_price_pence must be 0 or greater")

    for field, value in payload.items():
        setattr(event, field, value)

    if clear_photo_price:
        event.photo_price_pence = None

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


@router.get("/metrics", response_model=AdminMetricsOut, dependencies=[Depends(require_admin)])
def get_admin_metrics(
    range: str = Query(default="30d", pattern="^(7d|30d|90d|365d|all)$"),
    event_id: int | None = None,
    db: Session = Depends(get_db),
) -> AdminMetricsOut:
    now = datetime.now(timezone.utc)
    start_at = _range_start(range, now)

    if event_id is not None and not db.query(Event.id).filter(Event.id == event_id).first():
        raise HTTPException(404, "Event not found")

    created_orders = _orders_for_metrics(
        db,
        event_id=event_id,
        date_field=Order.created_at,
        start_at=start_at,
        end_at=now,
    )
    paid_orders = _orders_for_metrics(
        db,
        event_id=event_id,
        date_field=Order.paid_at,
        start_at=start_at,
        end_at=now,
    )

    money = _money_groups()
    status_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "subtotal": 0})
    daily: dict[str, AdminTrendPoint] = {}
    customer_totals: dict[str, dict] = {}
    event_totals: dict[str, dict] = {}
    photo_totals: dict[str, dict] = {}

    for order in created_orders:
        subtotal = _order_subtotal_pence(order)
        currency = _order_currency(order)
        status_key = order.status.value
        status_totals[status_key]["count"] += 1
        status_totals[status_key]["subtotal"] += subtotal
        if order.status == OrderStatus.PENDING:
            money[currency]["pending_value_pence"] += subtotal

        day_key = order.created_at.date().isoformat()
        if day_key not in daily:
            daily[day_key] = AdminTrendPoint(date=day_key)
        daily[day_key].order_count += 1
        daily[day_key].item_count += len(order.items)

    for order in paid_orders:
        subtotal = _order_subtotal_pence(order)
        discount = sum(max(0, item.discount_applied_pence) for item in order.items)
        currency = _order_currency(order)
        group = money[currency]
        group["gross_sales_pence"] += subtotal
        group["paid_revenue_pence"] += subtotal
        group["discount_pence"] += discount
        group["paid_order_count"] += 1
        if subtotal == 0:
            group["free_order_count"] += 1

        paid_day = (order.paid_at or order.created_at).date().isoformat()
        if paid_day not in daily:
            daily[paid_day] = AdminTrendPoint(date=paid_day)
        daily[paid_day].paid_order_count += 1
        daily[paid_day].revenue_by_currency[currency] = (
            daily[paid_day].revenue_by_currency.get(currency, 0) + subtotal
        )

        email = (order.email or "").strip().lower()
        if email:
            if email not in customer_totals:
                customer_totals[email] = {
                    "order_count": 0,
                    "paid_order_count": 0,
                    "last_order_at": order.paid_at or order.created_at,
                    "money": _money_groups(),
                }
            customer_totals[email]["order_count"] += 1
            customer_totals[email]["paid_order_count"] += 1
            customer_totals[email]["last_order_at"] = max(
                customer_totals[email]["last_order_at"],
                order.paid_at or order.created_at,
            )
            customer_totals[email]["money"][currency]["gross_sales_pence"] += subtotal
            customer_totals[email]["money"][currency]["paid_revenue_pence"] += subtotal
            customer_totals[email]["money"][currency]["paid_order_count"] += 1

        first_photo = order.items[0].photo if order.items and order.items[0].photo else None
        event = first_photo.event if first_photo else None
        event_slug = event.slug if event else (order.delivery.event_slug if order.delivery else "unknown")
        event_key = str(event.id if event else event_slug)
        if event_key not in event_totals:
            event_totals[event_key] = {
                "event_id": event.id if event else None,
                "event_slug": event_slug,
                "event_name": event.name if event else event_slug,
                "order_count": 0,
                "paid_order_count": 0,
                "item_count": 0,
                "money": _money_groups(),
            }
        event_totals[event_key]["order_count"] += 1
        event_totals[event_key]["paid_order_count"] += 1
        event_totals[event_key]["item_count"] += len(order.items)
        event_totals[event_key]["money"][currency]["gross_sales_pence"] += subtotal
        event_totals[event_key]["money"][currency]["paid_revenue_pence"] += subtotal
        event_totals[event_key]["money"][currency]["paid_order_count"] += 1

        for item in order.items:
            photo = item.photo
            photo_event = photo.event if photo else None
            if item.photo_id not in photo_totals:
                photo_totals[item.photo_id] = {
                    "photo_id": item.photo_id,
                    "event_slug": photo_event.slug if photo_event else None,
                    "event_name": photo_event.name if photo_event else None,
                    "item_count": 0,
                    "order_ids": set(),
                    "money": _money_groups(),
                }
            line_total = _line_total_pence(item)
            photo_totals[item.photo_id]["item_count"] += 1
            photo_totals[item.photo_id]["order_ids"].add(order.id)
            photo_totals[item.photo_id]["money"][currency]["gross_sales_pence"] += line_total
            photo_totals[item.photo_id]["money"][currency]["paid_revenue_pence"] += line_total
            photo_totals[item.photo_id]["money"][currency]["paid_order_count"] += 1

    delivery_counts: dict[str, int] = defaultdict(int)
    for order in created_orders:
        if order.delivery:
            delivery_counts[order.delivery.zip_status.value] += 1
        else:
            delivery_counts["NO_DELIVERY"] += 1

    comms_query = db.query(Communication)
    if start_at is not None:
        comms_query = comms_query.filter(Communication.created_at >= start_at)
    comms_query = comms_query.filter(Communication.created_at <= now)
    if event_id is not None:
        comms_query = comms_query.filter(Communication.order_id.in_(_event_order_ids(db, event_id)))
    email_counts: dict[str, int] = defaultdict(int)
    for comm in comms_query.all():
        email_counts[comm.status.value] += 1

    paid_customer_counts: dict[str, int] = defaultdict(int)
    for order in paid_orders:
        if order.email:
            paid_customer_counts[order.email.strip().lower()] += 1

    alerts = _build_operational_alerts(db, event_id=event_id, now=now)
    recent_activity = _admin_activity_feed(db, limit=12)

    valid_stripe_events = db.query(StripeEvent).filter(
        StripeEvent.stripe_event_id.like("evt_%")
    )
    last_valid_stripe_event = (
        valid_stripe_events
        .order_by(StripeEvent.received_at.desc())
        .first()
    )
    recent_valid_stripe_events = valid_stripe_events.filter(
        StripeEvent.received_at >= now - timedelta(hours=24)
    )
    stripe_webhook_health = AdminStripeWebhookHealth(
        secret_configured=bool(settings.STRIPE_WEBHOOK_SECRET),
        last_valid_event_at=(
            last_valid_stripe_event.received_at if last_valid_stripe_event else None
        ),
        last_event_type=(
            last_valid_stripe_event.event_type if last_valid_stripe_event else None
        ),
        valid_events_24h=recent_valid_stripe_events.count(),
        processed_events_24h=recent_valid_stripe_events.filter(
            StripeEvent.processing_status == "PROCESSED"
        ).count(),
        ignored_events_24h=recent_valid_stripe_events.filter(
            StripeEvent.processing_status == "IGNORED"
        ).count(),
    )

    totals = AdminMetricsTotals(
        total_orders=len(created_orders),
        paid_orders=len(paid_orders),
        pending_orders=sum(1 for order in created_orders if order.status == OrderStatus.PENDING),
        failed_orders=sum(1 for order in created_orders if order.status == OrderStatus.FAILED),
        ready_orders=sum(1 for order in created_orders if order.status == OrderStatus.READY),
        free_orders=sum(1 for order in paid_orders if _order_subtotal_pence(order) == 0),
        items_sold=sum(len(order.items) for order in paid_orders),
        unique_customers=len(paid_customer_counts),
        repeat_customers=sum(1 for count in paid_customer_counts.values() if count > 1),
        average_items_per_order=(
            round(sum(len(order.items) for order in paid_orders) / len(paid_orders), 2)
            if paid_orders else 0
        ),
    )

    return AdminMetricsOut(
        range=range,
        generated_at=now,
        start_at=start_at,
        end_at=now,
        event_id=event_id,
        mixed_currency=len(money.keys()) > 1,
        totals=totals,
        money=_money_metric_list(money),
        status_breakdown=[
            AdminBreakdownMetric(
                key=key,
                label=key.replace("_", " ").title(),
                count=values["count"],
                subtotal_pence=values["subtotal"],
            )
            for key, values in sorted(status_totals.items())
        ],
        delivery_health=[
            AdminBreakdownMetric(key=key, label=key.replace("_", " ").title(), count=count)
            for key, count in sorted(delivery_counts.items())
        ],
        email_health=[
            AdminBreakdownMetric(key=key, label=key.replace("_", " ").title(), count=count)
            for key, count in sorted(email_counts.items())
        ],
        top_events=[
            AdminEventMetric(
                event_id=values["event_id"],
                event_slug=values["event_slug"],
                event_name=values["event_name"],
                order_count=values["order_count"],
                paid_order_count=values["paid_order_count"],
                item_count=values["item_count"],
                gross_sales=_money_metric_list(values["money"]),
            )
            for values in sorted(
                event_totals.values(),
                key=lambda row: (row["paid_order_count"], row["item_count"]),
                reverse=True,
            )[:10]
        ],
        top_photos=[
            AdminPhotoMetric(
                photo_id=values["photo_id"],
                event_slug=values["event_slug"],
                event_name=values["event_name"],
                item_count=values["item_count"],
                order_count=len(values["order_ids"]),
                gross_sales=_money_metric_list(values["money"]),
            )
            for values in sorted(
                photo_totals.values(),
                key=lambda row: (row["item_count"], len(row["order_ids"])),
                reverse=True,
            )[:10]
        ],
        top_customers=[
            AdminCustomerMetric(
                email=email,
                order_count=values["order_count"],
                paid_order_count=values["paid_order_count"],
                last_order_at=values["last_order_at"],
                gross_sales=_money_metric_list(values["money"]),
            )
            for email, values in sorted(
                customer_totals.items(),
                key=lambda item: (item[1]["paid_order_count"], item[1]["last_order_at"]),
                reverse=True,
            )[:10]
        ],
        daily_trends=[daily[key] for key in sorted(daily.keys())],
        alerts=alerts,
        recent_activity=recent_activity,
        stripe_webhook_health=stripe_webhook_health,
    )


def _email_config_out() -> AdminEmailConfigOut:
    return AdminEmailConfigOut(
        email_enabled=settings.EMAIL_ENABLED,
        provider=settings.EMAIL_PROVIDER,
        from_address=settings.EMAIL_FROM_ADDRESS,
        from_name=settings.EMAIL_FROM_NAME,
        brevo_key_set=bool(settings.BREVO_API_KEY),
        support_email=settings.SUPPORT_EMAIL,
        order_email_required=settings.ORDER_EMAIL_REQUIRED,
    )


@router.get("/settings", response_model=AdminSettingsOut, dependencies=[Depends(require_admin)])
def get_admin_settings(db: Session = Depends(get_db)) -> AdminSettingsOut:
    app_settings = get_app_settings(db)
    return AdminSettingsOut(
        checkout={
            "default_photo_price_pence": app_settings.default_photo_price_pence,
            "currency": app_settings.currency,
            "allow_stripe_promotion_codes": app_settings.allow_stripe_promotion_codes,
        },
        stripe_secret_key_set=bool(settings.STRIPE_SECRET_KEY),
        stripe_webhook_secret_set=bool(settings.STRIPE_WEBHOOK_SECRET),
        public_base_url=settings.PUBLIC_BASE_URL,
        site_name=settings.SITE_NAME,
        site_tagline=settings.SITE_TAGLINE,
        email=_email_config_out(),
    )


@router.get("/storage/zip/status", dependencies=[Depends(require_admin)])
def get_zip_storage_status() -> dict:
    backend_constructed = True
    error = None
    try:
        get_zip_storage_backend()
    except Exception as exc:
        backend_constructed = False
        error = str(exc)

    return {
        "effective_backend": get_zip_storage_backend_name(),
        "storage_backend": settings.STORAGE_BACKEND,
        "zip_storage_backend": settings.ZIP_STORAGE_BACKEND or None,
        "r2_bucket": settings.R2_BUCKET,
        "r2_account_id_set": bool(settings.R2_ACCOUNT_ID),
        "r2_endpoint_url_set": bool(settings.R2_ENDPOINT_URL or settings.R2_ACCOUNT_ID),
        "r2_access_key_id_set": bool(settings.R2_ACCESS_KEY_ID),
        "r2_secret_access_key_set": bool(settings.R2_SECRET_ACCESS_KEY),
        "backend_constructed": backend_constructed,
        "error": error,
    }


@router.patch(
    "/settings/checkout",
    response_model=AdminSettingsOut,
    dependencies=[Depends(require_admin)],
)
def update_checkout_settings(
    req: AdminCheckoutSettingsUpdate,
    db: Session = Depends(get_db),
) -> AdminSettingsOut:
    app_settings = get_app_settings(db)
    payload = req.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "No fields supplied")

    if "default_photo_price_pence" in payload:
        price = payload["default_photo_price_pence"]
        if price is None or price < 0:
            raise HTTPException(400, "default_photo_price_pence must be 0 or greater")
        app_settings.default_photo_price_pence = price

    if "currency" in payload:
        currency = normalize_currency(payload["currency"] or "")
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise HTTPException(400, "currency must be a 3-letter ISO currency code")
        app_settings.currency = currency

    if "allow_stripe_promotion_codes" in payload:
        app_settings.allow_stripe_promotion_codes = bool(payload["allow_stripe_promotion_codes"])

    db.commit()
    db.refresh(app_settings)
    return get_admin_settings(db)


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


@router.get(
    "/events/{event_id}/photos/upload_status",
    response_model=PhotoUploadStatusesOut,
    dependencies=[Depends(require_admin)],
)
def get_photo_upload_status(
    event_id: int,
    photo_ids: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PhotoUploadStatusesOut:
    """Return proof/original presence for event photos.

    When photo_ids are supplied, every requested ID is returned, including
    IDs with no DB record. With no filter, all DB records for the event are
    returned.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    requested = list(dict.fromkeys(photo_ids or []))
    query = db.query(Photo).filter(Photo.event_id == event_id)
    if requested:
        query = query.filter(Photo.id.in_(requested))
    records = {photo.id: photo for photo in query.all()}
    output_ids = requested or sorted(records)
    storage_root = Path(settings.STORAGE_ROOT)

    statuses: list[PhotoUploadStatusOut] = []
    for photo_id in output_ids:
        photo = records.get(photo_id)
        proof_rel = (
            photo.proof_path if photo is not None
            else f"proofs/{event.slug}/{photo_id}.jpg"
        )
        original_rel = (
            photo.original_path if photo is not None
            else f"originals/{event.slug}/{photo_id}.jpg"
        )
        statuses.append(
            PhotoUploadStatusOut(
                photo_id=photo_id,
                record_exists=photo is not None,
                proof_file_exists=(storage_root / proof_rel).exists(),
                original_file_exists=(storage_root / original_rel).exists(),
                state=photo.state.value if photo is not None and photo.state else None,
            )
        )

    return PhotoUploadStatusesOut(photos=statuses)


@router.put(
    "/events/{event_id}/cover",
    response_model=EventCreatedOut,
    dependencies=[Depends(require_admin)],
)
def upload_event_cover(
    event_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> EventCreatedOut:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    cover_path, _ = _process_cover_upload(event, file)
    event.cover_path = cover_path
    event.cover_updated_at = datetime.now(timezone.utc)
    db.commit()
    return EventCreatedOut(id=event.id, slug=event.slug)


@router.delete(
    "/events/{event_id}/cover",
    response_model=EventCreatedOut,
    dependencies=[Depends(require_admin)],
)
def delete_event_cover(
    event_id: int,
    db: Session = Depends(get_db),
) -> EventCreatedOut:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")

    _delete_cover_file(event)
    event.cover_path = None
    event.cover_updated_at = None
    db.commit()
    return EventCreatedOut(id=event.id, slug=event.slug)


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

    if delete_files:
        _delete_cover_file(event)
    event.cover_path = None
    event.cover_updated_at = None
    db.flush()

    # Delete in FK-safe order, using the same subquery to avoid a Python-side list
    tags_deleted = (
        db.query(PhotoTag)
        .filter(PhotoTag.photo_id.in_(photo_subq))
        .delete(synchronize_session="fetch")
    )
    db.query(OrderItem).filter(OrderItem.photo_id.in_(photo_subq)).delete(synchronize_session="fetch")

    db.query(Delivery).filter(Delivery.event_slug == slug).delete(synchronize_session="fetch")
    db.query(Order).filter(
        Order.cart_id.in_(db.query(Cart.id).filter(Cart.event_id == event_id))
    ).update({Order.cart_id: None}, synchronize_session=False)
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
            for kind in ("proofs", "originals", "covers"):
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
    requested_photo_ids = {entry.photo_id for entry in req.tags if entry.photo_id}
    if requested_photo_ids:
        valid_photo_ids = {
            row[0]
            for row in (
                db.query(Photo.id)
                .filter(
                    Photo.event_id == event_id,
                    Photo.id.in_(requested_photo_ids),
                )
                .all()
            )
        }
        missing_photo_ids = sorted(requested_photo_ids - valid_photo_ids)
        if missing_photo_ids:
            preview = ", ".join(missing_photo_ids[:5])
            suffix = "" if len(missing_photo_ids) <= 5 else ", ..."
            raise HTTPException(
                400,
                (
                    "Bib tag upload contains photo_id values not found in this event: "
                    f"{preview}{suffix}"
                ),
            )

    if req.replace:
        db.query(PhotoTag).filter(
            PhotoTag.photo_id.in_(
                db.query(Photo.id).filter(Photo.event_id == event_id)
            ),
            PhotoTag.tag_type == "bib",
        ).delete(synchronize_session="fetch")

    for entry in req.tags:
        bib_value = entry.bib.strip()
        if not bib_value:
            continue

        exists = (
            db.query(PhotoTag)
            .filter(
                PhotoTag.photo_id == entry.photo_id,
                PhotoTag.tag_type == "bib",
                func.trim(PhotoTag.value) == bib_value,
            )
            .first()
        )
        if not exists:
            db.add(
                PhotoTag(
                    photo_id=entry.photo_id,
                    tag_type="bib",
                    value=bib_value,
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
        os.chmod(dest_path, 0o644)
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
    zip_status: DeliveryZipStatus | None = None,
    event_id: int | None = None,
    q: str | None = Query(default=None, description="Search by order id/email/event slug/token"),
    limit: int | None = Query(default=None, ge=1, le=500),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    sort: str = Query(default="id", pattern="^(id|created_at|paid_at|status|subtotal|items)$"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    paid_from: datetime | None = None,
    paid_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> AdminOrderListOut:
    if limit is not None:
        page_size = limit

    query, item_stats = _admin_order_query(
        db,
        status=status,
        zip_status=zip_status,
        event_id=event_id,
        q=q,
        created_from=created_from,
        created_to=created_to,
        paid_from=paid_from,
        paid_to=paid_to,
    )

    total = query.count()
    rows = (
        _apply_order_sort(query, item_stats, sort, direction)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    result: list[AdminOrderOut] = []
    for order, delivery, item_count, _subtotal_pence in rows:
        result.append(_to_admin_order_out(order, int(item_count or 0), delivery))

    return AdminOrderListOut(orders=result, total=total, page=page, page_size=page_size)


@router.get("/orders/export", dependencies=[Depends(require_admin)])
def export_orders(
    status: OrderStatus | None = None,
    zip_status: DeliveryZipStatus | None = None,
    event_id: int | None = None,
    q: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    paid_from: datetime | None = None,
    paid_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> Response:
    query, item_stats = _admin_order_query(
        db,
        status=status,
        zip_status=zip_status,
        event_id=event_id,
        q=q,
        created_from=created_from,
        created_to=created_to,
        paid_from=paid_from,
        paid_to=paid_to,
    )
    rows = _apply_order_sort(query, item_stats, "id", "desc").all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "order_id",
        "status",
        "zip_status",
        "email",
        "event_slug",
        "created_at",
        "paid_at",
        "item_count",
        "subtotal_pence",
        "currency",
        "download_count",
        "max_downloads",
        "expires_at",
        "stripe_session_id",
        "stripe_payment_intent_id",
    ])
    for order, delivery, item_count, _subtotal_pence in rows:
        writer.writerow([
            order.id,
            order.status.value,
            delivery.zip_status.value if delivery else "",
            order.email,
            delivery.event_slug if delivery else "",
            order.created_at.isoformat() if order.created_at else "",
            order.paid_at.isoformat() if order.paid_at else "",
            int(item_count or 0),
            _order_subtotal_pence(order),
            _order_currency(order),
            delivery.download_count if delivery else "",
            delivery.max_downloads if delivery else "",
            delivery.expires_at.isoformat() if delivery and delivery.expires_at else "",
            order.stripe_session_id,
            order.stripe_payment_intent_id or "",
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="admin-orders.csv"'},
    )


@router.get("/orders/{order_id}", response_model=AdminOrderDetailOut, dependencies=[Depends(require_admin)])
def get_order_detail(order_id: int, db: Session = Depends(get_db)) -> AdminOrderDetailOut:
    order = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(404, "Order not found")

    delivery = db.query(Delivery).filter(Delivery.order_id == order_id).first()
    base = _to_admin_order_out(order, len(order.items), delivery)
    return AdminOrderDetailOut(
        **base.model_dump(),
        items=[
            AdminOrderItemOut(
                photo_id=item.photo_id,
                unit_price_pence=item.unit_price_pence,
                discount_applied_pence=item.discount_applied_pence,
                line_total_pence=max(0, item.unit_price_pence - item.discount_applied_pence),
            )
            for item in sorted(order.items, key=lambda i: i.id)
        ],
    )


@router.get(
    "/orders/{order_id}/timeline",
    response_model=AdminOrderTimelineOut,
    dependencies=[Depends(require_admin)],
)
def get_order_timeline(order_id: int, db: Session = Depends(get_db)) -> AdminOrderTimelineOut:
    if not db.query(Order.id).filter(Order.id == order_id).first():
        raise HTTPException(404, "Order not found")
    return AdminOrderTimelineOut(entries=_admin_activity_feed(db, order_id=order_id, limit=100))


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

    record_order_activity(
        db,
        order_id=order_id,
        action="DELIVERY_RESET",
        message="Delivery access reset by admin",
        actor="admin",
        metadata={
            "rotate_token": req.rotate_token,
            "days_valid": req.days_valid,
            "max_downloads": delivery.max_downloads,
        },
    )
    db.commit()
    db.refresh(delivery)

    if settings.EMAIL_ENABLED and order.email:
        comm = Communication(
            order_id=order_id,
            kind=CommunicationKind.DELIVERY_RESET,
            status=CommunicationStatus.QUEUED,
            provider="brevo",
            recipient_email=order.email,
            subject="Your download link has been reset",
            template_key="DELIVERY_RESET",
            initiated_by="admin",
        )
        db.add(comm)
        record_order_activity(
            db,
            order_id=order_id,
            action="EMAIL_QUEUED",
            message="Delivery reset email queued",
            actor="admin",
            metadata={"kind": CommunicationKind.DELIVERY_RESET.value},
        )
        db.commit()
        enqueue_communication_after_commit(
            db,
            communication_id=comm.id,
            order_id=order_id,
            actor="admin",
        )

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
    record_order_activity(
        db,
        order_id=order_id,
        action="DELIVERY_EXPIRED",
        message="Delivery link expired by admin",
        actor="admin",
    )
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

    delivery = ensure_delivery_for_order(order, db)
    if delivery.zip_status == DeliveryZipStatus.BUILDING:
        raise HTTPException(409, "Order ZIP is already building")

    if order.status == OrderStatus.PAID:
        order.status = OrderStatus.READY
    delivery.zip_status = DeliveryZipStatus.BUILDING
    delivery.zip_error = None
    delivery.zip_deleted_at = None
    delivery.zip_expires_at = None
    record_order_activity(
        db,
        order_id=order_id,
        action="ZIP_REBUILD_QUEUED",
        message="ZIP rebuild queued by admin",
        actor="admin",
    )
    db.commit()

    celery_app.send_task("tasks.build_zip.build_zip", args=[order.id])

    db.refresh(order)
    db.refresh(delivery)
    item_count = db.query(OrderItem).filter(OrderItem.order_id == order_id).count()
    return _to_admin_order_out(order, item_count, delivery)


@router.get(
    "/orders/{order_id}/communications",
    response_model=list[CommunicationOut],
    dependencies=[Depends(require_admin)],
)
def list_communications(order_id: int, db: Session = Depends(get_db)) -> list[CommunicationOut]:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")

    comms = (
        db.query(Communication)
        .filter(Communication.order_id == order_id)
        .order_by(Communication.created_at.desc())
        .all()
    )
    return comms  # type: ignore[return-value]


@router.post(
    "/orders/{order_id}/communications/send",
    response_model=CommunicationOut,
    dependencies=[Depends(require_admin)],
)
def send_communication(
    order_id: int,
    req: AdminSendEmailRequest,
    db: Session = Depends(get_db),
) -> CommunicationOut:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    if not order.email:
        raise HTTPException(409, "Order has no email address")

    subject_map = {
        CommunicationKind.ORDER_CONFIRMED: "Your order is confirmed",
        CommunicationKind.DOWNLOAD_READY: "Your photos are ready to download",
        CommunicationKind.DELIVERY_RESET: "Your download link has been reset",
    }

    comm = Communication(
        order_id=order_id,
        kind=req.kind,
        status=CommunicationStatus.QUEUED,
        provider="brevo",
        recipient_email=order.email,
        subject=subject_map[req.kind],
        template_key=req.kind.value,
        initiated_by="admin",
    )
    db.add(comm)
    record_order_activity(
        db,
        order_id=order_id,
        action="EMAIL_QUEUED",
        message=f"{req.kind.value.replace('_', ' ').title()} email queued by admin",
        actor="admin",
        metadata={"kind": req.kind.value},
    )
    db.commit()
    db.refresh(comm)

    enqueue_communication_after_commit(
        db,
        communication_id=comm.id,
        order_id=order_id,
        actor="admin",
    )
    db.refresh(comm)

    return comm  # type: ignore[return-value]


@router.post(
    "/orders/{order_id}/stripe-sync",
    response_model=AdminStripeSyncOut,
    dependencies=[Depends(require_admin)],
)
def sync_order_with_stripe(order_id: int, db: Session = Depends(get_db)) -> AdminStripeSyncOut:
    if not settings.STRIPE_SECRET_KEY:
        return AdminStripeSyncOut(
            order_id=order_id,
            status="unconfigured",
            message="Stripe is not configured on this server",
            orders_checked=0,
            orders_updated=0,
        )

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    if not order.stripe_session_id or order.stripe_session_id.startswith(("pending_", "free_")):
        return AdminStripeSyncOut(
            order_id=order.id,
            status="skipped",
            message="Order does not have a Stripe Checkout session to sync",
            orders_checked=1,
            orders_updated=0,
        )

    try:
        session = _stripe_session_dict(stripe.checkout.Session.retrieve(order.stripe_session_id))
    except Exception as exc:
        record_order_activity(
            db,
            order_id=order.id,
            action="STRIPE_SYNC_FAILED",
            message="Stripe sync failed",
            actor="admin",
            metadata={"error": str(exc)},
        )
        db.commit()
        return AdminStripeSyncOut(
            order_id=order.id,
            status="failed",
            message=f"Stripe sync failed: {exc}",
            orders_checked=1,
            orders_updated=0,
        )

    stored = store_stripe_event(
        db,
        {
            "id": f"manual_sync_{order.id}_{uuid.uuid4()}",
            "type": "checkout.session.sync",
            "livemode": False,
            "created": int(datetime.now(timezone.utc).timestamp()),
            "data": {"object": session},
        },
    )
    changed, communication_id = _apply_stripe_session_to_order(order, session, db, actor="admin")
    stored.processing_status = "PROCESSED"
    stored.error_message = None
    if not changed:
        record_order_activity(
            db,
            order_id=order.id,
            action="STRIPE_SYNC_NO_CHANGE",
            message="Stripe sync found no order changes",
            actor="admin",
            metadata={"stripe_session_id": order.stripe_session_id},
        )
    db.commit()

    if communication_id:
        enqueue_communication_after_commit(
            db,
            communication_id=communication_id,
            order_id=order.id,
            actor="admin",
        )

    return AdminStripeSyncOut(
        order_id=order.id,
        status="updated" if changed else "unchanged",
        message="Order updated from Stripe" if changed else "Stripe sync completed with no changes",
        orders_checked=1,
        orders_updated=1 if changed else 0,
    )


@router.post(
    "/stripe/reconcile",
    response_model=AdminStripeSyncOut,
    dependencies=[Depends(require_admin)],
)
def reconcile_stale_stripe_orders(
    older_than_minutes: int = Query(default=15, ge=1, le=10080),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AdminStripeSyncOut:
    if not settings.STRIPE_SECRET_KEY:
        return AdminStripeSyncOut(
            status="unconfigured",
            message="Stripe is not configured on this server",
            orders_checked=0,
            orders_updated=0,
        )

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    orders = (
        db.query(Order)
        .filter(
            Order.status == OrderStatus.PENDING,
            Order.created_at <= cutoff,
            ~Order.stripe_session_id.startswith("pending_"),
            ~Order.stripe_session_id.startswith("free_"),
        )
        .order_by(Order.created_at.asc())
        .limit(limit)
        .all()
    )

    checked = 0
    updated = 0
    failures = 0
    communications_to_enqueue: list[tuple[int, int]] = []
    for order in orders:
        checked += 1
        try:
            session = _stripe_session_dict(stripe.checkout.Session.retrieve(order.stripe_session_id))
            stored = store_stripe_event(
                db,
                {
                    "id": f"manual_reconcile_{order.id}_{uuid.uuid4()}",
                    "type": "checkout.session.reconcile",
                    "livemode": False,
                    "created": int(datetime.now(timezone.utc).timestamp()),
                    "data": {"object": session},
                },
            )
            changed, communication_id = _apply_stripe_session_to_order(order, session, db, actor="admin")
            stored.processing_status = "PROCESSED"
            stored.error_message = None
            if changed:
                updated += 1
            if communication_id:
                communications_to_enqueue.append((communication_id, order.id))
        except Exception as exc:
            failures += 1
            record_order_activity(
                db,
                order_id=order.id,
                action="STRIPE_RECONCILE_FAILED",
                message="Stripe reconciliation failed",
                actor="admin",
                metadata={"error": str(exc), "stripe_session_id": order.stripe_session_id},
            )

    db.commit()
    for communication_id, order_id in communications_to_enqueue:
        enqueue_communication_after_commit(
            db,
            communication_id=communication_id,
            order_id=order_id,
            actor="admin",
        )
    return AdminStripeSyncOut(
        status="completed" if failures == 0 else "partial",
        message=f"Checked {checked} stale pending order(s); updated {updated}; failures {failures}.",
        orders_checked=checked,
        orders_updated=updated,
    )


# ── Email config & test ──────────────────────────────────────────────────────

@router.get("/email/config", response_model=AdminEmailConfigOut, dependencies=[Depends(require_admin)])
def get_email_config() -> AdminEmailConfigOut:
    """Return current email configuration as seen by the running process."""
    return _email_config_out()


@router.post("/email/test", response_model=AdminEmailTestOut, dependencies=[Depends(require_admin)])
def send_test_email(req: AdminEmailTestRequest) -> AdminEmailTestOut:
    """Send a test email directly (synchronous, not via Celery) for config verification."""
    provider_name = settings.EMAIL_PROVIDER if settings.EMAIL_ENABLED else "noop"

    if not settings.EMAIL_ENABLED:
        return AdminEmailTestOut(
            sent=False,
            email_enabled=False,
            provider=provider_name,
            from_address=settings.EMAIL_FROM_ADDRESS,
            message="EMAIL_ENABLED is False — no email sent",
        )

    try:
        provider = get_provider()
        provider_name = type(provider).__name__
        msg = EmailMessage(
            to_email=req.to_email,
            to_name=req.to_email,
            subject=f"[{settings.SITE_NAME}] Test email",
            html_body=(
                f"<p>This is a test email from <strong>{settings.SITE_NAME}</strong>.</p>"
                f"<p>If you received this, your email configuration is working correctly.</p>"
            ),
            text_body=(
                f"This is a test email from {settings.SITE_NAME}.\n\n"
                "If you received this, your email configuration is working correctly."
            ),
            from_email=settings.EMAIL_FROM_ADDRESS,
            from_name=settings.EMAIL_FROM_NAME,
        )
        message_id = provider.send(msg)
        return AdminEmailTestOut(
            sent=True,
            email_enabled=True,
            provider=provider_name,
            from_address=settings.EMAIL_FROM_ADDRESS,
            message=f"Sent OK — message_id: {message_id}",
        )
    except ProviderError as exc:
        return AdminEmailTestOut(
            sent=False,
            email_enabled=True,
            provider=provider_name,
            from_address=settings.EMAIL_FROM_ADDRESS,
            message=f"Provider error: {exc}",
        )
    except Exception as exc:
        return AdminEmailTestOut(
            sent=False,
            email_enabled=True,
            provider=provider_name,
            from_address=settings.EMAIL_FROM_ADDRESS,
            message=f"Unexpected error: {exc}",
        )
