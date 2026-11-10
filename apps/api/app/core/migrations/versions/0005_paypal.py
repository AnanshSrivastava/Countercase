"""PayPal support: evidence source 'paypal', event ledger, tracking number, processor metadata

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

OLD_SOURCES = "'stripe', 'shipping_api', 'shop_api', 'seller_upload', 'seller_claim'"
NEW_SOURCES = "'stripe', 'paypal', 'shipping_api', 'shop_api', 'seller_upload', 'seller_claim'"


def _set_sources(values: str) -> None:
    op.drop_constraint("evidence_source_valid", "evidence_items", type_="check")
    op.create_check_constraint("evidence_source_valid", "evidence_items", f"source IN ({values})")


def upgrade() -> None:
    _set_sources(NEW_SOURCES)
    op.add_column("disputes", sa.Column("tracking_number", sa.String(), nullable=True))
    op.add_column("disputes", sa.Column("processor_meta", sa.JSON(), nullable=True))
    op.create_table(
        "paypal_events",
        sa.Column("event_id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("event_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("paypal_events")
    op.drop_column("disputes", "processor_meta")
    op.drop_column("disputes", "tracking_number")
    op.execute("DELETE FROM evidence_items WHERE source = 'paypal'")
    _set_sources(OLD_SOURCES)
