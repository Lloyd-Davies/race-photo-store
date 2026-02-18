"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # events
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "ARCHIVED", name="eventstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("public_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archive_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.create_index("ix_events_slug", "events", ["slug"], unique=True)

    # ------------------------------------------------------------------
    # photos
    # ------------------------------------------------------------------
    op.create_table(
        "photos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proof_path", sa.String(), nullable=False),
        sa.Column("original_path", sa.String(), nullable=False),
        sa.Column(
            "state",
            sa.Enum("READY", "ARCHIVED_ONLY", "MISSING", name="photostate"),
            nullable=False,
            server_default="READY",
        ),
    )
    op.create_index("ix_photos_event_id", "photos", ["event_id"])

    # ------------------------------------------------------------------
    # photo_tags
    # ------------------------------------------------------------------
    op.create_table(
        "photo_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("photo_id", sa.String(), sa.ForeignKey("photos.id"), nullable=False),
        sa.Column("tag_type", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.UniqueConstraint("photo_id", "tag_type", "value", name="uq_photo_tags_photo_type_value"),
    )
    op.create_index("ix_photo_tags_photo_id", "photo_tags", ["photo_id"])

    # ------------------------------------------------------------------
    # carts
    # ------------------------------------------------------------------
    op.create_table(
        "carts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------------
    # orders
    # ------------------------------------------------------------------
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stripe_session_id", sa.String(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "PAID", "BUILDING", "READY", "FAILED", "EXPIRED",
                name="orderstatus",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_stripe_session_id", "orders", ["stripe_session_id"], unique=True)

    # ------------------------------------------------------------------
    # order_items
    # ------------------------------------------------------------------
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("photo_id", sa.String(), sa.ForeignKey("photos.id"), nullable=False),
        sa.Column("unit_price_pence", sa.Integer(), nullable=False),
        sa.Column("discount_applied_pence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    # ------------------------------------------------------------------
    # deliveries
    # ------------------------------------------------------------------
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("zip_path", sa.String(), nullable=False),
        sa.Column("event_slug", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_downloads", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.create_index("ix_deliveries_token", "deliveries", ["token"], unique=True)


def downgrade() -> None:
    op.drop_table("deliveries")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("carts")
    op.drop_table("photo_tags")
    op.drop_table("photos")
    op.drop_table("events")

    op.execute("DROP TYPE IF EXISTS orderstatus")
    op.execute("DROP TYPE IF EXISTS photostate")
    op.execute("DROP TYPE IF EXISTS eventstatus")
