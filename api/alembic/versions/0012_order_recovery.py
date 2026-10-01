"""Durable recovery work and a database-owned activation boundary."""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("recovery_activation", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False))
    op.execute("INSERT INTO recovery_activation VALUES (1, CURRENT_TIMESTAMP)")
    op.create_table("recovery_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.String()),
        sa.UniqueConstraint("kind", "target_id", name="uq_recovery_target"))
    op.create_index("ix_recovery_jobs_order_id", "recovery_jobs", ["order_id"])
    op.create_index("ix_recovery_jobs_next_attempt_at", "recovery_jobs", ["next_attempt_at"])


def downgrade():
    op.drop_table("recovery_jobs")
    op.drop_table("recovery_activation")
