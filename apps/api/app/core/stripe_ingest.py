"""Stripe `charge.dispute.*` webhook ingestion (F1).

Flow: verify signature on raw bytes -> dedupe by event id -> upsert dispute by
processor_dispute_id (so `.updated` before `.created` still works) -> classify new
disputes via the agent classifier.

Only extracted fields are stored. Raw payloads (billing details, card brand/last4)
are never persisted.
"""

import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import stripe
from sqlalchemy.orm import Session

from app.agent.classifier import classify
from app.core.collectors import EvidenceCollector, MockShop, collect_for_dispute
from app.core.disputes import ensure_seller
from app.core.hashing import customer_hash
from app.core.tables import DisputeRow, SellerRow, StripeEventRow
from app.settings import settings

log = logging.getLogger(__name__)

HANDLED_EVENTS = {"charge.dispute.created", "charge.dispute.updated", "charge.dispute.closed"}

# Stripe dispute.status -> our status. One place; anything not listed is ignored (status kept).
STRIPE_STATUS = {
    "warning_needs_response": "needs_response",
    "needs_response": "needs_response",
    "warning_under_review": "submitted",
    "under_review": "submitted",
    "won": "won",
    "prevented": "won",
    "warning_closed": "won",  # inquiry closed without becoming a chargeback
    "lost": "lost",
}
FALLBACK_DEADLINE = timedelta(days=7)  # only if Stripe sends no due_by on first sight


class SignatureError(Exception):
    pass


class WebhookNotConfigured(Exception):
    pass


def verify_and_parse(payload: bytes, sig_header: str | None) -> dict:
    if not settings.stripe_webhook_secret:
        raise WebhookNotConfigured("STRIPE_WEBHOOK_SECRET is not set")
    try:
        stripe.WebhookSignature.verify_header(
            payload.decode("utf-8"), sig_header, settings.stripe_webhook_secret, tolerance=300
        )
    except (stripe.SignatureVerificationError, ValueError, UnicodeDecodeError) as exc:
        raise SignatureError(str(exc)) from exc
    return json.loads(payload)


@dataclass
class ChargeInfo:
    """What we may learn about the charge. `identifier` is hashed immediately and never stored."""

    identifier: str | None = None
    metadata: dict = field(default_factory=dict)


def fetch_charge_info(charge_id: str | None) -> ChargeInfo:
    """Look up the charge for a customer identifier and order metadata.

    Network call; tests replace it.
    """
    key = settings.stripe_secret_key
    if not charge_id or not key.startswith(("sk_test_", "rk_test_")) or key.endswith("xxx"):
        return ChargeInfo()
    try:
        # StripeObject is not a dict in stripe>=15: convert before reading.
        charge = stripe.StripeClient(key).charges.retrieve(charge_id).to_dict()
        email = (charge.get("billing_details") or {}).get("email") or charge.get("receipt_email")
        customer = charge.get("customer")
        if isinstance(customer, dict):
            customer = customer.get("id")
    except Exception:  # enrichment is best-effort; never lose the dispute over it
        log.warning("charge lookup failed for %s", charge_id, exc_info=True)
        return ChargeInfo()
    return ChargeInfo(identifier=email or customer, metadata=dict(charge.get("metadata") or {}))


ChargeLookup = Callable[[str | None], ChargeInfo]


def safe_classify(reason: str) -> tuple[str | None, str | None, bool]:
    """Agent classifier (rules-only, fast). On failure the dispute is stored for review."""
    try:
        result = classify("stripe", reason)
        return result.category, result.explanation, result.needs_review
    except Exception:
        log.warning("classify failed for reason %r", reason, exc_info=True)
        return None, None, True


def next_status(current: str | None, stripe_status: str | None) -> str | None:
    """Map Stripe's status without regressing the seller's own workflow."""
    target = STRIPE_STATUS.get(stripe_status or "")
    if current is None:
        return target or "needs_response"
    if target is None or current == "accepted":  # seller chose to accept: keep it
        return current
    if target == "needs_response" and current in ("drafted", "approved", "submitted"):
        return current
    if current in ("won", "lost") and target not in ("won", "lost"):
        return current
    return target


def _ts(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, tz=UTC) if value else None


def _resolve_seller(session: Session, account_id: str | None) -> str:
    if account_id:
        seller = session.query(SellerRow).filter_by(processor_account_id=account_id).one_or_none()
        if seller:
            return seller.id
    return ensure_seller(session, settings.default_seller_id).id


def default_collector() -> EvidenceCollector:
    return MockShop(settings.default_seller_id)


def handle_event(
    session: Session,
    event: dict,
    charge_lookup: ChargeLookup = fetch_charge_info,
    collector: EvidenceCollector | None = None,
) -> str:
    """Apply one verified event. Returns a short outcome label (for logs and tests)."""
    event_id, event_type = event["id"], event["type"]
    if event_type not in HANDLED_EVENTS:
        return "ignored"
    if session.get(StripeEventRow, event_id):
        return "duplicate"

    obj = event["data"]["object"]
    event_at = _ts(event.get("created")) or datetime.now(UTC)
    row = session.query(DisputeRow).filter_by(processor_dispute_id=obj["id"]).one_or_none()

    if row is not None and row.last_event_at and event_at < row.last_event_at:
        outcome = "stale"
    elif row is None:
        row = _create(
            session, obj, event, event_at, charge_lookup, collector or default_collector()
        )
        outcome = "created"
    else:
        _update(row, obj, event_at)
        outcome = "updated"

    session.add(StripeEventRow(event_id=event_id, type=event_type, event_created_at=event_at))
    session.commit()
    return outcome


def _create(
    session: Session,
    obj: dict,
    event: dict,
    event_at: datetime,
    charge_lookup: ChargeLookup,
    collector: EvidenceCollector,
) -> DisputeRow:
    seller_id = _resolve_seller(session, event.get("account"))
    charge_id = obj.get("charge")
    try:
        info = charge_lookup(charge_id)
    except Exception:  # best-effort enrichment; the dispute row matters more
        log.warning("charge lookup raised for %s", charge_id, exc_info=True)
        info = ChargeInfo()
    evidence = obj.get("evidence") or {}
    identifier = evidence.get("customer_email_address") or info.identifier or charge_id or obj["id"]
    created_at = _ts(obj.get("created")) or event_at
    due_by = _ts((obj.get("evidence_details") or {}).get("due_by"))
    reason = obj.get("reason") or "general"
    category, explanation, needs_review = safe_classify(reason)
    meta = {**info.metadata, **(obj.get("metadata") or {})}

    row = DisputeRow(
        id="dp_" + secrets.token_hex(6),
        seller_id=seller_id,
        processor="stripe",
        processor_dispute_id=obj["id"],
        processor_charge_id=charge_id,
        processor_status=obj.get("status"),
        amount=obj["amount"],
        currency=obj["currency"],
        reason_raw=reason,
        category=category,
        category_explanation=explanation,
        category_needs_review=needs_review,
        status=next_status(None, obj.get("status")),
        created_at=created_at,
        deadline_at=due_by or created_at + FALLBACK_DEADLINE,
        customer_hash=customer_hash(seller_id, identifier),
        order_id=meta.get("order_id"),
        product_sku=meta.get("product_sku"),
        courier=meta.get("courier"),
        last_event_at=event_at,
    )
    session.add(row)
    session.flush()
    collect_for_dispute(session, row, collector)  # F4: never raises, never loses the dispute
    return row


def _update(row: DisputeRow, obj: dict, event_at: datetime) -> None:
    row.processor_status = obj.get("status") or row.processor_status
    row.status = next_status(row.status, obj.get("status"))
    row.amount = obj.get("amount", row.amount)
    due_by = _ts((obj.get("evidence_details") or {}).get("due_by"))
    if due_by:  # some updates omit due_by: keep the previous deadline
        row.deadline_at = due_by
    row.last_event_at = event_at
