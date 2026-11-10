"""submission audit columns and one active submission per dispute

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("letter_sha256", sa.String(), nullable=True))
    op.add_column("submissions", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("submissions", sa.Column("detail", sa.JSON(), nullable=True))
    # submit=true is final: never allow two live submissions for one dispute.
    op.create_index(
        "one_active_submission",
        "submissions",
        ["dispute_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'submitted')"),
    )


def downgrade() -> None:
    op.drop_index("one_active_submission", table_name="submissions")
    op.drop_column("submissions", "detail")
    op.drop_column("submissions", "note")
    op.drop_column("submissions", "letter_sha256")
