"""EvidenceCollector interface (F4). The mock shop implements it today; a Shopify/WooCommerce
adapter can replace it later without touching ingestion.

Rules every collector must follow (product principle 3, never fabricate):
- Return only facts read from a real system of record. If nothing can be matched with certainty,
  return an empty Collection.
- Never put raw personal data (emails, names, street addresses) in `summary`.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.core.models import EvidenceSource, EvidenceType


@dataclass(frozen=True)
class DisputeContext:
    seller_id: str
    dispute_id: str
    order_id: str | None  # explicit order reference, e.g. from Stripe charge metadata
    customer_hash: str
    amount: int
    currency: str
    created_at: datetime
    processor_charge_id: str | None = None  # PayPal: the seller transaction id


@dataclass(frozen=True)
class CollectedItem:
    type: EvidenceType
    source: EvidenceSource
    ref: str  # stable id of the underlying record (order, shipment, message); drives idempotent ids
    summary: str
    captured_at: datetime
    uri: str | None = None


@dataclass
class Collection:
    items: list[CollectedItem] = field(default_factory=list)
    # Verified facts about the order, used to fill gaps on the dispute row.
    order_id: str | None = None
    product_sku: str | None = None
    courier: str | None = None
    tracking_number: str | None = None


class EvidenceCollector(Protocol):
    def collect(self, ctx: DisputeContext) -> Collection: ...
