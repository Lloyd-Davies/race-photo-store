"""add communications table

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "communications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("kind", sa.Enum("ORDER_CONFIRMED", "DOWNLOAD_READY", "DELIVERY_RESET", name="communicationkind"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("recipient_email", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("template_key", sa.String(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.String(), nullable=True),
        sa.Column("status", sa.Enum("QUEUED", "SENT", "FAILED", "DELIVERED", "BOUNCED", "BLOCKED", "DEFERRED", name="communicationstatus"), nullable=False, server_default="QUEUED"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("provider_response_json", sa.JSON(), nullable=True),
        sa.Column("initiated_by", sa.String(), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )

    op.create_index("ix_communications_order_id", "communications", ["order_id"])
    op.create_index("ix_communications_provider_message_id", "communications", ["provider_message_id"])
    op.create_index("ix_communications_order_id_kind", "communications", ["order_id", "kind"])

    # Partial unique index — prevents duplicate automatic sends at the DB layer
    op.execute(
        "CREATE UNIQUE INDEX uq_communications_dedupe_key "
        "ON communications (dedupe_key) WHERE dedupe_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_communications_dedupe_key")
    op.drop_index("ix_communications_order_id_kind", "communications")
    op.drop_index("ix_communications_provider_message_id", "communications")
    op.drop_index("ix_communications_order_id", "communications")
    op.drop_table("communications")
    op.execute("DROP TYPE IF EXISTS communicationstatus")
    op.execute("DROP TYPE IF EXISTS communicationkind")
