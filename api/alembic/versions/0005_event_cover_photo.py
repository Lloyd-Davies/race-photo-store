"""add event cover image

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("cover_path", sa.String(), nullable=True))
    op.add_column("events", sa.Column("cover_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "cover_updated_at")
    op.drop_column("events", "cover_path")
