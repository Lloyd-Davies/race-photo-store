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
    is_password_protected: bool = False
    access_hint: Optional[str] = None
    public_until: Optional[datetime] = None
    archive_after: Optional[datetime] = None

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
    order_access_token: str


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
    is_password_protected: bool = False
    access_secret: Optional[str] = None
    access_password: Optional[str] = None
    access_hint: Optional[str] = None


class UpdateEventRequest(BaseModel):
    name: Optional[str] = None
    date: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[EventStatus] = None
    is_password_protected: Optional[bool] = None
    access_secret: Optional[str] = None
    access_password: Optional[str] = None
    clear_access_secret: Optional[bool] = None
    clear_access_password: Optional[bool] = None
    access_hint: Optional[str] = None
    public_until: Optional[datetime] = None
    archive_after: Optional[datetime] = None


class EventUnlockRequest(BaseModel):
    secret: Optional[str] = None
    password: Optional[str] = None


class EventUnlockOut(BaseModel):
    access_token: str
    expires_at: datetime


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
    replace: bool = False  # When True, clears existing bib tags for the event before inserting


class BibTagsResult(BaseModel):
    added: int


class PhotoUploadResult(BaseModel):
    photo_id: str
    kind: str        # "original" | "proof"
    size_bytes: int
    created: bool    # True → new DB record, False → updated existing


class PhotoIdsOut(BaseModel):
    photo_ids: list[str]


class DeleteEventResult(BaseModel):
    slug: str
    photos_deleted: int
    tags_deleted: int
    orders_affected: int
    files_deleted: bool


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


class AdminStatsOut(BaseModel):
    total_events: int
    total_photos: int
    total_orders: int
    total_deliveries: int
    pending_orders: int
    failed_orders: int
    active_events: int


class AdminLoginRequest(BaseModel):
    admin_token: str


class AdminRefreshRequest(BaseModel):
    refresh_token: str


class AdminSessionOut(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
