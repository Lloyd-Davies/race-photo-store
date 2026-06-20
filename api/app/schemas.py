from datetime import datetime
import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from photostore.models import (
    CommunicationKind,
    CommunicationStatus,
    DeliveryZipStatus,
    EventStatus,
    OrderStatus,
)

EVENT_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_event_slug(slug: str) -> str:
    if not EVENT_SLUG_RE.fullmatch(slug):
        raise ValueError("slug must contain lowercase letters, numbers, and single hyphens only")
    if slug.isdigit():
        raise ValueError("slug must not be all numeric")
    return slug


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
    photo_price_pence: Optional[int] = None
    effective_photo_price_pence: int
    currency: str
    cover_url: Optional[str] = None

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
    email: Optional[EmailStr] = None

    @model_validator(mode="after")
    def require_email_in_production(self) -> "CheckoutRequest":
        from photostore.config import settings
        if settings.ORDER_EMAIL_REQUIRED and not self.email:
            raise ValueError("email is required")
        return self


class CheckoutOut(BaseModel):
    order_id: int
    stripe_checkout_url: Optional[str] = None
    order_access_token: str


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class OrderDownloadItemOut(BaseModel):
    photo_id: str
    proof_url: Optional[str] = None
    view_url: Optional[str] = None
    download_url: str


class OrderZipOut(BaseModel):
    status: DeliveryZipStatus = DeliveryZipStatus.NOT_REQUESTED
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    status: OrderStatus
    download_url: Optional[str] = None
    zip: OrderZipOut = Field(default_factory=OrderZipOut)
    items: list[OrderDownloadItemOut] = Field(default_factory=list)
    download_items: list[OrderDownloadItemOut] = Field(default_factory=list)

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
    photo_price_pence: Optional[int] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        return validate_event_slug(value)


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
    photo_price_pence: Optional[int] = None
    clear_photo_price: Optional[bool] = None


class EventUnlockRequest(BaseModel):
    secret: Optional[str] = None
    password: Optional[str] = None


class EventUnlockOut(BaseModel):
    access_token: str
    expires_at: datetime


class EventCreatedOut(BaseModel):
    id: int
    slug: str


class AdminEventOut(EventOut):
    photo_count: int = 0
    order_count: int = 0


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


class PhotoUploadStatusOut(BaseModel):
    photo_id: str
    record_exists: bool
    proof_file_exists: bool
    original_file_exists: bool
    state: Optional[str] = None


class PhotoUploadStatusesOut(BaseModel):
    photos: list[PhotoUploadStatusOut]


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
    subtotal_pence: int = 0
    currency: str = "GBP"
    event_slug: Optional[str] = None
    download_count: Optional[int] = None
    max_downloads: Optional[int] = None
    expires_at: Optional[datetime] = None
    download_url: Optional[str] = None
    zip_status: Optional[DeliveryZipStatus] = None
    zip_expires_at: Optional[datetime] = None
    zip_error: Optional[str] = None


class AdminOrderListOut(BaseModel):
    orders: list[AdminOrderOut]
    total: int = 0
    page: int = 1
    page_size: int = 100


class AdminOrderItemOut(BaseModel):
    photo_id: str
    unit_price_pence: int
    discount_applied_pence: int
    line_total_pence: int


class AdminOrderDetailOut(AdminOrderOut):
    items: list[AdminOrderItemOut] = Field(default_factory=list)


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


class AdminMoneyMetric(BaseModel):
    currency: str
    gross_sales_pence: int = 0
    paid_revenue_pence: int = 0
    pending_value_pence: int = 0
    discount_pence: int = 0
    paid_order_count: int = 0
    free_order_count: int = 0
    average_order_value_pence: int = 0


class AdminBreakdownMetric(BaseModel):
    key: str
    label: str
    count: int
    subtotal_pence: int = 0


class AdminTrendPoint(BaseModel):
    date: str
    order_count: int = 0
    paid_order_count: int = 0
    item_count: int = 0
    revenue_by_currency: dict[str, int] = Field(default_factory=dict)


class AdminEventMetric(BaseModel):
    event_id: Optional[int] = None
    event_slug: str
    event_name: str
    order_count: int = 0
    paid_order_count: int = 0
    item_count: int = 0
    gross_sales: list[AdminMoneyMetric] = Field(default_factory=list)


class AdminPhotoMetric(BaseModel):
    photo_id: str
    event_slug: Optional[str] = None
    event_name: Optional[str] = None
    item_count: int = 0
    order_count: int = 0
    gross_sales: list[AdminMoneyMetric] = Field(default_factory=list)


class AdminCustomerMetric(BaseModel):
    email: str
    order_count: int = 0
    paid_order_count: int = 0
    last_order_at: Optional[datetime] = None
    gross_sales: list[AdminMoneyMetric] = Field(default_factory=list)


class AdminOperationalAlert(BaseModel):
    type: str
    severity: str
    count: int
    message: str
    order_ids: list[int] = Field(default_factory=list)


class AdminActivityOut(BaseModel):
    id: int
    source: str
    action: str
    actor: Optional[str] = None
    message: str
    status: Optional[str] = None
    order_id: Optional[int] = None
    created_at: datetime
    metadata: dict = Field(default_factory=dict)


class AdminMetricsTotals(BaseModel):
    total_orders: int = 0
    paid_orders: int = 0
    pending_orders: int = 0
    failed_orders: int = 0
    ready_orders: int = 0
    free_orders: int = 0
    items_sold: int = 0
    unique_customers: int = 0
    repeat_customers: int = 0
    average_items_per_order: float = 0


class AdminStripeWebhookHealth(BaseModel):
    secret_configured: bool = False
    last_valid_event_at: Optional[datetime] = None
    last_event_type: Optional[str] = None
    valid_events_24h: int = 0
    processed_events_24h: int = 0
    ignored_events_24h: int = 0


class AdminMetricsOut(BaseModel):
    range: str
    generated_at: datetime
    start_at: Optional[datetime] = None
    end_at: datetime
    event_id: Optional[int] = None
    mixed_currency: bool = False
    totals: AdminMetricsTotals
    money: list[AdminMoneyMetric] = Field(default_factory=list)
    status_breakdown: list[AdminBreakdownMetric] = Field(default_factory=list)
    delivery_health: list[AdminBreakdownMetric] = Field(default_factory=list)
    email_health: list[AdminBreakdownMetric] = Field(default_factory=list)
    top_events: list[AdminEventMetric] = Field(default_factory=list)
    top_photos: list[AdminPhotoMetric] = Field(default_factory=list)
    top_customers: list[AdminCustomerMetric] = Field(default_factory=list)
    daily_trends: list[AdminTrendPoint] = Field(default_factory=list)
    alerts: list[AdminOperationalAlert] = Field(default_factory=list)
    recent_activity: list[AdminActivityOut] = Field(default_factory=list)
    stripe_webhook_health: AdminStripeWebhookHealth


class AdminOrderTimelineOut(BaseModel):
    entries: list[AdminActivityOut]


class AdminStripeSyncOut(BaseModel):
    order_id: Optional[int] = None
    status: str
    message: str
    orders_checked: int = 0
    orders_updated: int = 0


class AdminLoginRequest(BaseModel):
    admin_token: str


class AdminRefreshRequest(BaseModel):
    refresh_token: str


class AdminSessionOut(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


class CommunicationOut(BaseModel):
    id: int
    kind: CommunicationKind
    status: CommunicationStatus
    recipient_email: str
    subject: str
    initiated_by: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class AdminSendEmailRequest(BaseModel):
    kind: CommunicationKind


class AdminEmailConfigOut(BaseModel):
    email_enabled: bool
    provider: str
    from_address: str
    from_name: str
    brevo_key_set: bool
    support_email: str
    order_email_required: bool


class AdminEmailTestRequest(BaseModel):
    to_email: EmailStr


class AdminEmailTestOut(BaseModel):
    sent: bool
    email_enabled: bool
    provider: str
    from_address: str
    message: str


class AdminCheckoutSettingsOut(BaseModel):
    default_photo_price_pence: int
    currency: str
    allow_stripe_promotion_codes: bool


class AdminSettingsOut(BaseModel):
    checkout: AdminCheckoutSettingsOut
    stripe_secret_key_set: bool
    stripe_webhook_secret_set: bool
    public_base_url: str
    site_name: str
    site_tagline: str
    email: AdminEmailConfigOut


class AdminCheckoutSettingsUpdate(BaseModel):
    default_photo_price_pence: Optional[int] = None
    currency: Optional[str] = None
    allow_stripe_promotion_codes: Optional[bool] = None
