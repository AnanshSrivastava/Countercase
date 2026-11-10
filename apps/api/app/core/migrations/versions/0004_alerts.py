"""deadline alerts (72h / 24h / 6h), at most one per dispute and threshold

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "dispute_id",
            sa.String(),
            sa.ForeignKey("disputes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("threshold_hours", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("to_address", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("threshold_hours IN (72, 24, 6)", name="alerts_threshold_valid"),
        sa.CheckConstraint("channel IN ('email', 'simulated')", name="alerts_channel_valid"),
        sa.CheckConstraint(
            "status IN ('sent', 'failed', 'superseded')", name="alerts_status_valid"
        ),
        sa.UniqueConstraint("dispute_id", "threshold_hours", name="alerts_one_per_threshold"),
    )
    op.create_index("ix_alerts_dispute_id", "alerts", ["dispute_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_dispute_id", table_name="alerts")
    op.drop_table("alerts")
