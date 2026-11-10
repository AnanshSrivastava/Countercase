"""Postgres schema for core.

Field names follow docs/CONTRACTS.md. Enum columns are text + CHECK built from the Literal
types in models.py, so there is one source of truth.

Privacy: no raw Stripe payloads, card data, emails or addresses are stored.
Customers are stored only as HMAC hashes.
"""

from datetime import datetime
from typing import Any, get_args

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import (
    Category,
    DisputeStatus,
    EvidenceSource,
    EvidenceType,
    MemoryMode,
    SubmissionStatus,
)


def one_of(column: str, literal: Any) -> str:
    values = ", ".join(f"'{v}'" for v in get_args(literal))
    return f"{column} IN ({values})"


TS = DateTime(timezone=True)


class SellerRow(Base):
    __tablename__ = "sellers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    processor: Mapped[str] = mapped_column(String, default="stripe")
    processor_account_id: Mapped[str | None] = mapped_column(String, unique=True)
    currency: Mapped[str] = mapped_column(String, default="usd")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class DisputeRow(Base):
    __tablename__ = "disputes"
    __table_args__ = (
        CheckConstraint(one_of("category", Category), name="disputes_category_valid"),
        CheckConstraint(one_of("status", DisputeStatus), name="disputes_status_valid"),
        CheckConstraint("amount >= 0", name="disputes_amount_non_negative"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    seller_id: Mapped[str] = mapped_column(ForeignKey("sellers.id"), index=True)
    processor: Mapped[str] = mapped_column(String)
    processor_dispute_id: Mapped[str] = mapped_column(String, unique=True)
    processor_charge_id: Mapped[str | None] = mapped_column(String)
    processor_status: Mapped[str | None] = mapped_column(String)
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String)
    reason_raw: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    category_explanation: Mapped[str | None] = mapped_column(Text)
    category_needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TS)
    deadline_at: Mapped[datetime] = mapped_column(TS, index=True)
    customer_hash: Mapped[str] = mapped_column(String, index=True)
    order_id: Mapped[str | None] = mapped_column(String)
    product_sku: Mapped[str | None] = mapped_column(String)
    courier: Mapped[str | None] = mapped_column(String)
    last_event_at: Mapped[datetime | None] = mapped_column(TS)
    # Verified shipment tracking number (from the shop collector); PayPal fulfilment proof needs it.
    tracking_number: Mapped[str | None] = mapped_column(String)
    # Processor-specific facts that have no column of their own (PayPal life-cycle stage, outcome).
    processor_meta: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())

    evidence: Mapped[list["EvidenceRow"]] = relationship(
        back_populates="dispute", order_by="EvidenceRow.captured_at"
    )


class EvidenceRow(Base):
    __tablename__ = "evidence_items"
    __table_args__ = (
        CheckConstraint(one_of("type", EvidenceType), name="evidence_type_valid"),
        CheckConstraint(one_of("source", EvidenceSource), name="evidence_source_valid"),
        # Product rule: anything the seller supplied (notes, claims, uploads) is never verified.
        CheckConstraint(
            "NOT (verified AND (type IN ('seller_note', 'seller_upload') "
            "OR source IN ('seller_claim', 'seller_upload')))",
            name="evidence_seller_claims_unverified",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dispute_id: Mapped[str] = mapped_column(
        ForeignKey("disputes.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)
    verified: Mapped[bool] = mapped_column(Boolean)
    summary: Mapped[str] = mapped_column(Text)
    uri: Mapped[str | None] = mapped_column(String)
    captured_at: Mapped[datetime] = mapped_column(TS)

    dispute: Mapped[DisputeRow] = relationship(back_populates="evidence")


class DraftRow(Base):
    __tablename__ = "drafts"
    __table_args__ = (
        CheckConstraint(one_of("memory_mode", MemoryMode), name="drafts_memory_mode_valid"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dispute_id: Mapped[str] = mapped_column(
        ForeignKey("disputes.id", ondelete="CASCADE"), index=True
    )
    memory_mode: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)  # contract Draft object as returned by the agent
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class SubmissionRow(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(one_of("status", SubmissionStatus), name="submissions_status_valid"),
        # At most one live submission per dispute: submit=true is final, so never two in flight.
        Index(
            "one_active_submission",
            "dispute_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'submitted')"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dispute_id: Mapped[str] = mapped_column(
        ForeignKey("disputes.id", ondelete="CASCADE"), index=True
    )
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("drafts.id"))
    letter_md: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    approved_at: Mapped[datetime] = mapped_column(
        TS
    )  # seller approval is required before any submit
    submitted_at: Mapped[datetime | None] = mapped_column(TS)
    letter_sha256: Mapped[str | None] = mapped_column(String)  # what the seller reviewed
    note: Mapped[str | None] = mapped_column(Text)  # human-readable outcome, e.g. export reason
    detail: Mapped[dict | None] = mapped_column(JSON)  # audit: claims, edits, attachments, sizes
    pdf_uri: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class StripeEventRow(Base):
    """Processed webhook event ids for idempotency. Metadata only, never the payload."""

    __tablename__ = "stripe_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String)
    event_created_at: Mapped[datetime] = mapped_column(TS)
    received_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class PayPalEventRow(Base):
    """Processed PayPal webhook event ids for idempotency. Metadata only, never the payload."""

    __tablename__ = "paypal_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String)
    event_created_at: Mapped[datetime] = mapped_column(TS)
    received_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class AlertRow(Base):
    """A deadline warning that was (or was meant to be) sent. One per dispute and threshold."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("dispute_id", "threshold_hours", name="alerts_one_per_threshold"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dispute_id: Mapped[str] = mapped_column(
        ForeignKey("disputes.id", ondelete="CASCADE"), index=True
    )
    threshold_hours: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String)  # email | simulated
    status: Mapped[str] = mapped_column(String)  # sent | failed | superseded
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    to_address: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(TS, server_default=func.now())
