"""add per-event asset migration tracking

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


asset_type = postgresql.ENUM("PROOFS", "ORIGINALS", name="assettype", create_type=False)
migration_status = postgresql.ENUM(
    "NOT_STARTED",
    "QUEUED",
    "RUNNING",
    "READY",
    "FAILED",
    name="assetmigrationstatus",
    create_type=False,
)


def upgrade() -> None:
    asset_type.create(op.get_bind(), checkfirst=True)
    migration_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "event_asset_migrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_type", asset_type, nullable=False),
        sa.Column(
            "status",
            migration_status,
            nullable=False,
            server_default="NOT_STARTED",
        ),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("migrated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.UniqueConstraint(
            "event_id",
            "asset_type",
            name="uq_event_asset_migrations_event_type",
        ),
    )
    op.create_index(
        "ix_event_asset_migrations_event_id",
        "event_asset_migrations",
        ["event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_asset_migrations_event_id", table_name="event_asset_migrations")
    op.drop_table("event_asset_migrations")
    migration_status.drop(op.get_bind(), checkfirst=True)
    asset_type.drop(op.get_bind(), checkfirst=True)
