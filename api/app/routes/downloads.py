from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.deps import get_db
from app.rate_limit import enforce_rate_limit
from photostore.config import settings
from photostore.models import Delivery, OrderItem, Photo

router = APIRouter(tags=["downloads"])


def _get_valid_delivery(token: str, db: Session) -> Delivery:
    delivery = db.query(Delivery).filter(Delivery.token == token).first()

    if not delivery:
        raise HTTPException(404, "Download link not found")

    if datetime.now(timezone.utc) > delivery.expires_at:
        raise HTTPException(410, "Download link has expired")

    if delivery.download_count >= delivery.max_downloads:
        raise HTTPException(410, "Download limit reached")

    return delivery


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


@router.get("/d/{token}")
def download(token: str, request: Request, db: Session = Depends(get_db)) -> Response:
    enforce_rate_limit(request, scope="download", limit=90, window_seconds=60)

    delivery = _get_valid_delivery(token, db)

    zip_abs_path = Path(settings.STORAGE_ROOT) / delivery.zip_path
    if not zip_abs_path.exists():
        raise HTTPException(409, "ZIP is not ready yet")

    # Increment before responding so partial connections still consume a count
    delivery.download_count += 1
    db.commit()

    # zip_path is stored as "zips/order-<id>.zip"; strip the directory prefix
    # so that X-Accel-Redirect maps to the nginx internal location /_internal_zips/
    zip_filename = delivery.zip_path.split("/")[-1]

    filename = f"event-{delivery.event_slug}-order-{delivery.order_id}.zip"

    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/_internal_zips/{zip_filename}",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/zip",
        },
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
    original_abs, original_rel = _safe_storage_relative_path(photo.original_path, "originals")

    if not original_abs.exists():
        raise HTTPException(404, "Original image not found")

    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/_internal_originals/{original_rel.as_posix()}",
            "Content-Disposition": (
                f'attachment; filename="{_attachment_filename(delivery.event_slug, photo_id)}"'
            ),
            "Content-Type": "image/jpeg",
        },
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
    proof_abs, proof_rel = _safe_storage_relative_path(photo.proof_path, "proofs")

    if not proof_abs.exists():
        raise HTTPException(404, "Proof image not found")

    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/_internal_proofs/{proof_rel.as_posix()}",
            "Content-Type": "image/jpeg",
            "Cache-Control": "private, max-age=3600",
        },
    )
