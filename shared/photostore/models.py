import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EventStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class PhotoState(str, enum.Enum):
    READY = "READY"
    ARCHIVED_ONLY = "ARCHIVED_ONLY"
    MISSING = "MISSING"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    BUILDING = "BUILDING"
    READY = "READY"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    location = Column(String)
    status = Column(Enum(EventStatus), nullable=False, default=EventStatus.ACTIVE)
    is_password_protected = Column(Boolean, nullable=False, default=False)
    access_password_hash = Column(String)
    access_hint = Column(String)
    public_until = Column(DateTime(timezone=True))
    archive_after = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow)

    photos = relationship("Photo", back_populates="event")


class Photo(Base):
    __tablename__ = "photos"

    # id matches the filename stem (e.g. "DSC_0001")
    id = Column(String, primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True))
    proof_path = Column(String, nullable=False)      # e.g. proofs/<slug>/<id>.jpg
    original_path = Column(String, nullable=False)   # e.g. originals/<slug>/<id>.jpg
    state = Column(Enum(PhotoState), nullable=False, default=PhotoState.READY)

    event = relationship("Event", back_populates="photos")
    tags = relationship("PhotoTag", back_populates="photo")


class PhotoTag(Base):
    __tablename__ = "photo_tags"

    id = Column(Integer, primary_key=True)
    photo_id = Column(String, ForeignKey("photos.id"), nullable=False, index=True)
    tag_type = Column(String, nullable=False)   # e.g. "bib"
    value = Column(String, nullable=False)       # e.g. "123"
    confidence = Column(Float)

    __table_args__ = (UniqueConstraint("photo_id", "tag_type", "value"),)

    photo = relationship("Photo", back_populates="tags")


class Cart(Base):
    __tablename__ = "carts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    email = Column(String)
    items_json = Column(JSON, nullable=False)   # list[str] of photo_id
    created_at = Column(DateTime(timezone=True), default=utcnow)
    expires_at = Column(DateTime(timezone=True))


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    stripe_session_id = Column(String, unique=True, nullable=False, index=True)
    stripe_payment_intent_id = Column(String)
    email = Column(String, nullable=False)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    paid_at = Column(DateTime(timezone=True))

    items = relationship("OrderItem", back_populates="order")
    delivery = relationship("Delivery", back_populates="order", uselist=False)


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    photo_id = Column(String, ForeignKey("photos.id"), nullable=False)
    unit_price_pence = Column(Integer, nullable=False)
    discount_applied_pence = Column(Integer, nullable=False, default=0)

    order = relationship("Order", back_populates="items")
    photo = relationship("Photo")


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    zip_path = Column(String, nullable=False)          # e.g. zips/order-123.zip
    event_slug = Column(String, nullable=False)        # for Content-Disposition filename
    expires_at = Column(DateTime(timezone=True), nullable=False)
    max_downloads = Column(Integer, nullable=False, default=5)
    download_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    order = relationship("Order", back_populates="delivery")
