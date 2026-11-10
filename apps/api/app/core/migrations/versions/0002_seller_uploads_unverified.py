"""seller uploads can never be verified evidence

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NAME = "evidence_seller_claims_unverified"


def upgrade() -> None:
    op.drop_constraint(NAME, "evidence_items", type_="check")
    op.create_check_constraint(
        NAME,
        "evidence_items",
        "NOT (verified AND (type IN ('seller_note', 'seller_upload') "
        "OR source IN ('seller_claim', 'seller_upload')))",
    )


def downgrade() -> None:
    op.drop_constraint(NAME, "evidence_items", type_="check")
    op.create_check_constraint(
        NAME,
        "evidence_items",
        "NOT (verified AND (type = 'seller_note' OR source = 'seller_claim'))",
    )
