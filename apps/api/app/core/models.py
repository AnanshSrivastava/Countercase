"""Pydantic models mirroring docs/CONTRACTS.md v0.2. Keep in sync with the contract and fixtures."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "not_received",
    "unauthorized",
    "not_as_described",
    "duplicate",
    "subscription_cancelled",
    "refund_not_processed",
    "other",
]
DisputeStatus = Literal[
    "needs_response", "drafted", "approved", "submitted", "won", "lost", "accepted"
]
EvidenceType = Literal[
    "order_receipt",
    "delivery_proof",
    "tracking",
    "ip_device",
    "prior_orders",
    "customer_message",
    "refund_policy",
    "seller_upload",
    "seller_note",
]
EvidenceSource = Literal[
    "stripe", "paypal", "shipping_api", "shop_api", "seller_upload", "seller_claim"
]
MemoryMode = Literal["on", "off"]
SubmissionStatus = Literal["pending", "submitted", "exported", "failed"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Dispute(Contract):
    id: str
    seller_id: str
    processor: str
    processor_dispute_id: str
    amount: int  # minor units
    currency: str
    reason_raw: str
    category: Category | None = None  # set by the agent classifier
    category_explanation: str | None = None  # v0.2
    status: DisputeStatus
    created_at: datetime
    deadline_at: datetime
    customer_hash: str
    order_id: str | None = None
    product_sku: str | None = None
    courier: str | None = None
    evidence: list[str] = []


class EvidenceItem(Contract):
    id: str
    dispute_id: str
    type: EvidenceType
    source: EvidenceSource
    verified: bool
    summary: str
    uri: str | None = None
    captured_at: datetime

    @model_validator(mode="after")
    def seller_input_is_never_verified(self) -> "EvidenceItem":
        seller_supplied = self.type in ("seller_note", "seller_upload") or self.source in (
            "seller_claim",
            "seller_upload",
        )
        if seller_supplied and self.verified:
            raise ValueError(
                "seller-supplied evidence (note, claim, upload) must have verified=false"
            )
        return self


class Seller(Contract):  # v0.2
    id: str
    name: str
    processor: str
    processor_account_id: str | None = None
    currency: str
    created_at: datetime


class Submission(Contract):  # v0.2
    id: str
    dispute_id: str
    draft_id: str | None = None
    letter_md: str
    status: SubmissionStatus
    approved_at: datetime  # seller approval is required before anything is submitted
    submitted_at: datetime | None = None
    pdf_uri: str | None = None
    error: str | None = None
    note: str | None = None  # v0.4


class DisputeDetail(Contract):
    """Response of GET /core/disputes/{id}; same shape as fixtures/disputes/*.json (D-4)."""

    dispute: Dispute
    evidence: list[EvidenceItem]


class Claim(Contract):
    """One sentence of the response and the verified evidence item that backs it."""

    text: str = Field(min_length=1, max_length=1000)
    evidence_id: str


class LetterRequest(Contract):  # v0.4
    """What the seller reviewed. Used by letter-preview, draft save and approve."""

    claims: list[Claim] = Field(max_length=30)
    seller_statement: str | None = Field(default=None, max_length=2000)
    # Seller uploads to attach to the response. Notes are private and never sent;
    # an upload is attached only if it is listed here.
    attach_upload_ids: list[str] = Field(default_factory=list, max_length=10)
    # The agent's original claims, kept only for the edit audit trail.
    agent_claims: list[Claim] | None = Field(default=None, max_length=30)


class BlockedClaim(Contract):
    index: int
    evidence_id: str
    reason: str


class LetterPreview(Contract):  # v0.4
    letter_md: str
    letter_sha256: str
    blocked: list[BlockedClaim]
    attachments: list[str]  # seller-provided files that will be attached, by display name


class ApproveRequest(LetterRequest):  # v0.4
    approved: bool
    letter_sha256: str  # from the preview the seller reviewed; a mismatch means review again


class AcceptRequest(Contract):  # v0.4
    confirm: bool


class AcceptResult(Contract):  # v0.4
    status: DisputeStatus
    closed_at_processor: bool
    note: str


class Alert(Contract):  # v0.5
    """A deadline warning. `channel == "simulated"` means no email was really delivered."""

    id: str
    dispute_id: str
    threshold_hours: Literal[72, 24, 6]
    channel: Literal["email", "simulated"]
    status: Literal["sent", "failed", "superseded"]
    subject: str
    body: str
    to_address: str | None = None
    error: str | None = None
    sent_at: datetime | None = None
