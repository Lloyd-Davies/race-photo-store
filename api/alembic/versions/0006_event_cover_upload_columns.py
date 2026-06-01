"""ensure event cover upload columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _event_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns("events")}


def upgrade() -> None:
    columns = _event_columns()

    if "cover_path" not in columns:
        op.add_column("events", sa.Column("cover_path", sa.String(), nullable=True))
    if "cover_updated_at" not in columns:
        op.add_column("events", sa.Column("cover_updated_at", sa.DateTime(timezone=True), nullable=True))

    if "cover_photo_id" in columns:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        for fk in inspector.get_foreign_keys("events"):
            if fk.get("constrained_columns") == ["cover_photo_id"] and fk.get("name"):
                op.drop_constraint(fk["name"], "events", type_="foreignkey")
        op.drop_column("events", "cover_photo_id")


def downgrade() -> None:
    # This migration only repairs environments that saw the old uncommitted
    # 0005 draft. The canonical 0005 schema already owns the upload-cover
    # columns, so downgrading from 0006 to 0005 should leave them intact.
    pass
