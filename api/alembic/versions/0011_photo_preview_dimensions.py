"""add stored public preview dimensions

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("preview_width", sa.Integer(), nullable=True))
    op.add_column("photos", sa.Column("preview_height", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("photos", "preview_height")
    op.drop_column("photos", "preview_width")
