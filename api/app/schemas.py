from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from photostore.models import EventStatus, OrderStatus


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class EventOut(BaseModel):
    id: int
    slug: str
    name: str
    date: datetime
    location: Optional[str] = None
    status: EventStatus

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------


class PhotoOut(BaseModel):
    photo_id: str
    proof_url: str
    captured_at: Optional[datetime] = None


class PhotoListOut(BaseModel):
    photos: list[PhotoOut]
    total: int
    page: int
    pages: int


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


class CreateCartRequest(BaseModel):
    event_id: int
    photo_ids: list[str]
    email: Optional[str] = None


class CartOut(BaseModel):
    cart_id: UUID
    count: int


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    cart_id: UUID


class CheckoutOut(BaseModel):
    order_id: int
    stripe_checkout_url: str


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class OrderOut(BaseModel):
    id: int
    status: OrderStatus
    download_url: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class CreateEventRequest(BaseModel):
    slug: str
    name: str
    date: datetime
    location: Optional[str] = None


class EventCreatedOut(BaseModel):
    id: int
    slug: str


class IngestResult(BaseModel):
    ingested: int
    skipped: int


class BibTagEntry(BaseModel):
    photo_id: str
    bib: str
    confidence: float = 1.0


class BibTagsRequest(BaseModel):
    tags: list[BibTagEntry]


class BibTagsResult(BaseModel):
    added: int


class AdminOrderOut(BaseModel):
    id: int
    status: OrderStatus
    email: str
    created_at: datetime
    paid_at: Optional[datetime] = None
    item_count: int
    event_slug: Optional[str] = None
    download_count: Optional[int] = None
    max_downloads: Optional[int] = None
    expires_at: Optional[datetime] = None
    download_url: Optional[str] = None


class AdminOrderListOut(BaseModel):
    orders: list[AdminOrderOut]


class AdminResetDeliveryRequest(BaseModel):
    rotate_token: bool = True
    days_valid: int = 30
    max_downloads: Optional[int] = None
