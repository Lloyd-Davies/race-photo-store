"""add delivery zip lifecycle fields

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


zip_status_enum = sa.Enum(
    "NOT_REQUESTED",
    "BUILDING",
    "READY",
    "EXPIRED",
    "FAILED",
    name="deliveryzipstatus",
)


def upgrade() -> None:
    bind = op.get_bind()
    zip_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "deliveries",
        sa.Column(
            "zip_status",
            zip_status_enum,
            nullable=False,
            server_default="NOT_REQUESTED",
        ),
    )
    op.add_column("deliveries", sa.Column("zip_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deliveries", sa.Column("zip_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deliveries", sa.Column("zip_deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deliveries", sa.Column("zip_error", sa.String(), nullable=True))

    op.execute(
        """
        UPDATE deliveries
        SET
            zip_status = 'READY',
            zip_created_at = COALESCE(created_at, now()),
            zip_expires_at = now() + interval '3 days'
        WHERE zip_path IS NOT NULL
        """
    )

    op.alter_column(
        "deliveries",
        "zip_path",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.execute(
        """
        UPDATE deliveries
        SET zip_path = 'zips/order-' || order_id || '.zip'
        WHERE zip_path IS NULL
        """
    )
    op.alter_column(
        "deliveries",
        "zip_path",
        existing_type=sa.String(),
        nullable=False,
    )

    op.drop_column("deliveries", "zip_error")
    op.drop_column("deliveries", "zip_deleted_at")
    op.drop_column("deliveries", "zip_expires_at")
    op.drop_column("deliveries", "zip_created_at")
    op.drop_column("deliveries", "zip_status")

    zip_status_enum.drop(bind, checkfirst=True)
