from datetime import datetime, timezone
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.deps import get_db
from app.rate_limit import enforce_rate_limit
from photostore.config import settings
from photostore.models import Delivery, DeliveryZipStatus, OrderItem, Photo
from photostore.storage import (
    InvalidStorageKey,
    get_original_storage_backend,
    get_proof_storage_backend,
    get_zip_storage_backend,
)

router = APIRouter(tags=["downloads"])
logger = logging.getLogger(__name__)


def _get_valid_delivery(token: str, db: Session) -> Delivery:
    delivery = db.query(Delivery).filter(Delivery.token == token).first()

    if not delivery:
        raise HTTPException(404, "Download link not found")

    if datetime.now(timezone.utc) > delivery.expires_at:
        raise HTTPException(410, "Download link has expired")

    return delivery


def _zip_expired(delivery: Delivery) -> bool:
    return bool(
        delivery.zip_expires_at
        and datetime.now(timezone.utc) > delivery.zip_expires_at
    )


def _zip_not_ready(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message})


def _safe_storage_relative_path(path: str, storage_subdir: str) -> tuple[Path, Path]:
    storage_root = Path(settings.STORAGE_ROOT)
    file_abs = (storage_root / path).resolve()
    subdir_root = (storage_root / storage_subdir).resolve()
    try:
        file_rel = file_abs.relative_to(subdir_root)
    except ValueError:
        raise HTTPException(500, "Invalid image path")
    return file_abs, file_rel


def _purchased_photo(delivery: Delivery, photo_id: str, db: Session) -> Photo:
    item = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == delivery.order_id, OrderItem.photo_id == photo_id)
        .first()
    )
    if not item:
        raise HTTPException(404, "Photo not found for this order")

    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(404, "Photo not found")

    return photo


def _attachment_filename(event_slug: str, photo_id: str) -> str:
    safe_event = event_slug.replace('"', "").replace("/", "-").replace("\\", "-")
    safe_photo = photo_id.replace('"', "").replace("/", "-").replace("\\", "-")
    return f"{safe_event}-{safe_photo}.jpg"


def _purchased_asset_response(
    *,
    storage,
    key: str,
    storage_subdir: str,
    internal_location: str,
    disposition: str | None = None,
    cache_control: str | None = None,
    missing_detail: str,
) -> Response:
    if not storage.is_local:
        try:
            if storage.exists(key):
                return RedirectResponse(
                    storage.presigned_get_url(
                        key,
                        response_content_disposition=disposition,
                        response_content_type="image/jpeg",
                    ),
                    status_code=302,
                    headers={"Cache-Control": cache_control or "no-store"},
                )
        except Exception:
            logger.warning("Purchased asset R2 read failed; using local fallback", exc_info=True)

    asset_abs, asset_rel = _safe_storage_relative_path(key, storage_subdir)
    if not asset_abs.exists():
        raise HTTPException(404, missing_detail)
    headers = {
        "X-Accel-Redirect": f"/{internal_location}/{asset_rel.as_posix()}",
        "Content-Type": "image/jpeg",
    }
    if disposition:
        headers["Content-Disposition"] = disposition
    if cache_control:
        headers["Cache-Control"] = cache_control
    return Response(status_code=200, headers=headers)


@router.get("/d/{token}")
def download(token: str, request: Request, db: Session = Depends(get_db)) -> Response:
    enforce_rate_limit(request, scope="download", limit=90, window_seconds=60)

    delivery = _get_valid_delivery(token, db)

    if delivery.download_count >= delivery.max_downloads:
        raise HTTPException(410, "Download limit reached")

    status = delivery.zip_status or DeliveryZipStatus.NOT_REQUESTED
    if status == DeliveryZipStatus.NOT_REQUESTED:
        return _zip_not_ready(409, "ZIP has not been prepared")
    if status == DeliveryZipStatus.BUILDING:
        return _zip_not_ready(202, "ZIP is being prepared")
    if status == DeliveryZipStatus.FAILED:
        return _zip_not_ready(409, "ZIP generation failed. Regenerate it from the order page.")
    if status == DeliveryZipStatus.EXPIRED:
        return _zip_not_ready(409, "ZIP has expired. Regenerate it from the order page.")
    if not delivery.zip_path:
        return _zip_not_ready(409, "ZIP has not been prepared")

    if _zip_expired(delivery):
        delivery.zip_status = DeliveryZipStatus.EXPIRED
        delivery.zip_deleted_at = datetime.now(timezone.utc)
        db.commit()
        return _zip_not_ready(409, "ZIP has expired. Regenerate it from the order page.")

    storage = get_zip_storage_backend()
    try:
        zip_exists = storage.exists(delivery.zip_path)
    except InvalidStorageKey:
        zip_exists = False
    if not zip_exists:
        delivery.zip_status = DeliveryZipStatus.EXPIRED
        delivery.zip_deleted_at = datetime.now(timezone.utc)
        db.commit()
        return _zip_not_ready(409, "ZIP has expired. Regenerate it from the order page.")

    # Increment before responding so partial connections still consume a count
    delivery.download_count += 1
    db.commit()

    # zip_path is stored as "zips/order-<id>.zip"; strip the directory prefix
    # so that X-Accel-Redirect maps to the nginx internal location /_internal_zips/
    zip_filename = delivery.zip_path.split("/")[-1]

    filename = f"event-{delivery.event_slug}-order-{delivery.order_id}.zip"

    if storage.is_local:
        return Response(
            status_code=200,
            headers={
                "X-Accel-Redirect": f"/_internal_zips/{zip_filename}",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "application/zip",
            },
        )

    return RedirectResponse(
        storage.presigned_get_url(
            delivery.zip_path,
            response_content_disposition=f'attachment; filename="{filename}"',
            response_content_type="application/zip",
        ),
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/d/{token}/photos/{photo_id}/view")
def view_photo(
    token: str,
    photo_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    enforce_rate_limit(
        request,
        scope="photo-view",
        limit=240,
        window_seconds=60,
        suffix=token,
    )

    delivery = _get_valid_delivery(token, db)
    photo = _purchased_photo(delivery, photo_id, db)
    return _purchased_asset_response(
        storage=get_original_storage_backend(),
        key=photo.original_path,
        storage_subdir="originals",
        internal_location="_internal_originals",
        disposition=f'inline; filename="{_attachment_filename(delivery.event_slug, photo_id)}"',
        cache_control="private, max-age=3600",
        missing_detail="Original image not found",
    )


@router.get("/d/{token}/photos/{photo_id}")
def download_photo(
    token: str,
    photo_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    enforce_rate_limit(
        request,
        scope="photo-download",
        limit=240,
        window_seconds=60,
        suffix=token,
    )

    delivery = _get_valid_delivery(token, db)
    photo = _purchased_photo(delivery, photo_id, db)
    return _purchased_asset_response(
        storage=get_original_storage_backend(),
        key=photo.original_path,
        storage_subdir="originals",
        internal_location="_internal_originals",
        disposition=f'attachment; filename="{_attachment_filename(delivery.event_slug, photo_id)}"',
        missing_detail="Original image not found",
    )


@router.get("/d/{token}/photos/{photo_id}/proof")
def download_photo_proof(
    token: str,
    photo_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    enforce_rate_limit(
        request,
        scope="photo-proof",
        limit=360,
        window_seconds=60,
        suffix=token,
    )

    delivery = _get_valid_delivery(token, db)
    photo = _purchased_photo(delivery, photo_id, db)
    return _purchased_asset_response(
        storage=get_proof_storage_backend(),
        key=photo.proof_path,
        storage_subdir="proofs",
        internal_location="_internal_proofs",
        cache_control="private, max-age=3600",
        missing_detail="Proof image not found",
    )
