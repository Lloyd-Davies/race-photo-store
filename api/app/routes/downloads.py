from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.deps import get_db
from photostore.config import settings
from photostore.models import Delivery

router = APIRouter(tags=["downloads"])


@router.get("/d/{token}")
def download(token: str, db: Session = Depends(get_db)) -> Response:
    delivery = db.query(Delivery).filter(Delivery.token == token).first()

    if not delivery:
        raise HTTPException(404, "Download link not found")

    if datetime.now(timezone.utc) > delivery.expires_at:
        raise HTTPException(410, "Download link has expired")

    if delivery.download_count >= delivery.max_downloads:
        raise HTTPException(410, "Download limit reached")

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
