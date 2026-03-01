"""add event password lock fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("is_password_protected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("events", sa.Column("access_password_hash", sa.String(), nullable=True))
    op.add_column("events", sa.Column("access_hint", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "access_hint")
    op.drop_column("events", "access_password_hash")
    op.drop_column("events", "is_password_protected")
