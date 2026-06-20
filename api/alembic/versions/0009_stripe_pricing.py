"""add authoritative Stripe pricing and refund data

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("stripe_amount_subtotal_pence", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("stripe_discount_pence", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("stripe_tax_pence", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("stripe_shipping_pence", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("stripe_amount_paid_pence", sa.Integer(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("stripe_amount_refunded_pence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("stripe_pricing_status", sa.String(), nullable=False, server_default="UNSYNCED"),
    )
    op.add_column("orders", sa.Column("stripe_pricing_error", sa.String(), nullable=True))
    op.add_column("orders", sa.Column("stripe_pricing_synced_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "order_discounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("stripe_discount_id", sa.String(), nullable=True),
        sa.Column("stripe_promotion_code_id", sa.String(), nullable=True),
        sa.Column("promotion_code", sa.String(), nullable=True),
        sa.Column("stripe_coupon_id", sa.String(), nullable=True),
        sa.Column("amount_pence", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "order_id",
            "stripe_discount_id",
            name="uq_order_discounts_order_stripe_id",
        ),
    )
    op.create_index("ix_order_discounts_order_id", "order_discounts", ["order_id"])
    op.create_index("ix_order_discounts_stripe_discount_id", "order_discounts", ["stripe_discount_id"])
    op.create_index(
        "ix_order_discounts_stripe_promotion_code_id",
        "order_discounts",
        ["stripe_promotion_code_id"],
    )
    op.create_index("ix_order_discounts_promotion_code", "order_discounts", ["promotion_code"])

    op.create_table(
        "order_refunds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("stripe_refund_id", sa.String(), nullable=False),
        sa.Column("amount_pence", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("stripe_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("stripe_refund_id", name="uq_order_refunds_stripe_refund_id"),
    )
    op.create_index("ix_order_refunds_order_id", "order_refunds", ["order_id"])
    op.create_index("ix_order_refunds_stripe_refund_id", "order_refunds", ["stripe_refund_id"])

    op.execute(
        """
        UPDATE orders
        SET stripe_amount_subtotal_pence = 0,
            stripe_discount_pence = 0,
            stripe_tax_pence = 0,
            stripe_shipping_pence = 0,
            stripe_amount_paid_pence = 0,
            stripe_pricing_status = 'SYNCED',
            stripe_pricing_synced_at = COALESCE(paid_at, created_at)
        WHERE stripe_session_id LIKE 'free_%'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_order_refunds_stripe_refund_id", table_name="order_refunds")
    op.drop_index("ix_order_refunds_order_id", table_name="order_refunds")
    op.drop_table("order_refunds")
    op.drop_index("ix_order_discounts_promotion_code", table_name="order_discounts")
    op.drop_index("ix_order_discounts_stripe_promotion_code_id", table_name="order_discounts")
    op.drop_index("ix_order_discounts_stripe_discount_id", table_name="order_discounts")
    op.drop_index("ix_order_discounts_order_id", table_name="order_discounts")
    op.drop_table("order_discounts")

    op.drop_column("orders", "stripe_pricing_synced_at")
    op.drop_column("orders", "stripe_pricing_error")
    op.drop_column("orders", "stripe_pricing_status")
    op.drop_column("orders", "stripe_amount_refunded_pence")
    op.drop_column("orders", "stripe_amount_paid_pence")
    op.drop_column("orders", "stripe_shipping_pence")
    op.drop_column("orders", "stripe_tax_pence")
    op.drop_column("orders", "stripe_discount_pence")
    op.drop_column("orders", "stripe_amount_subtotal_pence")
