import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas import CartOut, CreateCartRequest
from photostore.models import Cart, Photo

router = APIRouter(prefix="/api", tags=["cart"])

CART_TTL_HOURS = 24


@router.post("/carts", response_model=CartOut)
def create_cart(req: CreateCartRequest, db: Session = Depends(get_db)) -> CartOut:
    # Deduplicate photo IDs while preserving order
    photo_ids = list(dict.fromkeys(req.photo_ids))

    if not photo_ids:
        raise HTTPException(400, "photo_ids must not be empty")

    # Validate all photos exist and belong to the requested event
    found = (
        db.query(Photo.id)
        .filter(Photo.id.in_(photo_ids), Photo.event_id == req.event_id)
        .all()
    )
    found_ids = {row.id for row in found}
    missing = [pid for pid in photo_ids if pid not in found_ids]
    if missing:
        raise HTTPException(400, f"Photo IDs not found in this event: {missing}")

    cart = Cart(
        id=uuid.uuid4(),
        event_id=req.event_id,
        email=req.email,
        items_json=photo_ids,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=CART_TTL_HOURS),
    )
    db.add(cart)
    db.commit()

    return CartOut(cart_id=cart.id, count=len(photo_ids))
