"""add checkout settings and event pricing

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("photo_price_pence", sa.Integer(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("currency", sa.String(), nullable=False, server_default="GBP"),
    )

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("default_photo_price_pence", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("currency", sa.String(), nullable=False, server_default="GBP"),
        sa.Column("allow_stripe_promotion_codes", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.execute(
        "INSERT INTO app_settings "
        "(id, default_photo_price_pence, currency, allow_stripe_promotion_codes) "
        "VALUES (1, 500, 'GBP', false)"
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_column("orders", "currency")
    op.drop_column("events", "photo_price_pence")
