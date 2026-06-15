"""add admin order analytics tables

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("cart_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_orders_cart_id_carts", "orders", "carts", ["cart_id"], ["id"])
    op.create_index("ix_orders_cart_id", "orders", ["cart_id"])

    op.create_table(
        "order_activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("actor", sa.String(), nullable=False, server_default="system"),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_order_activity_order_id", "order_activity", ["order_id"])
    op.create_index(
        "ix_order_activity_order_id_created_at",
        "order_activity",
        ["order_id", "created_at"],
    )

    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stripe_event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("stripe_session_id", sa.String(), nullable=True),
        sa.Column("payment_intent_id", sa.String(), nullable=True),
        sa.Column("livemode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("processing_status", sa.String(), nullable=False, server_default="RECEIVED"),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("stripe_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_stripe_events_stripe_event_id", "stripe_events", ["stripe_event_id"], unique=True)
    op.create_index("ix_stripe_events_event_type", "stripe_events", ["event_type"])
    op.create_index("ix_stripe_events_order_id", "stripe_events", ["order_id"])
    op.create_index("ix_stripe_events_stripe_session_id", "stripe_events", ["stripe_session_id"])
    op.create_index("ix_stripe_events_payment_intent_id", "stripe_events", ["payment_intent_id"])


def downgrade() -> None:
    op.drop_index("ix_stripe_events_payment_intent_id", table_name="stripe_events")
    op.drop_index("ix_stripe_events_stripe_session_id", table_name="stripe_events")
    op.drop_index("ix_stripe_events_order_id", table_name="stripe_events")
    op.drop_index("ix_stripe_events_event_type", table_name="stripe_events")
    op.drop_index("ix_stripe_events_stripe_event_id", table_name="stripe_events")
    op.drop_table("stripe_events")

    op.drop_index("ix_order_activity_order_id_created_at", table_name="order_activity")
    op.drop_index("ix_order_activity_order_id", table_name="order_activity")
    op.drop_table("order_activity")

    op.drop_index("ix_orders_cart_id", table_name="orders")
    op.drop_constraint("fk_orders_cart_id_carts", "orders", type_="foreignkey")
    op.drop_column("orders", "cart_id")
