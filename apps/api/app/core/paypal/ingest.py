"""PayPal `CUSTOMER.DISPUTE.*` webhook ingestion.

Same flow and guarantees as stripe_ingest: verify -> dedupe by event id -> upsert by
processor_dispute_id (so UPDATED before CREATED still works) -> classify -> collect evidence.
Only extracted fields are stored. The buyer's identity is hashed immediately and never persisted.
"""

from __future__ import annotations

import json
import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agent.classifier import classify
from app.core.collectors import EvidenceCollector, collect_for_dispute
from app.core.hashing import customer_hash
from app.core.paypal import mapping
from app.core.paypal.client import PayPalClient, PayPalError
from app.core.stripe_ingest import (
    FALLBACK_DEADLINE,
    _resolve_seller,
    default_collector,
    next_status,
)
from app.core.tables import DisputeRow, PayPalEventRow
from app.settings import settings

log = logging.getLogger(__name__)

HANDLED_EVENTS = {
    "CUSTOMER.DISPUTE.CREATED",
    "CUSTOMER.DISPUTE.UPDATED",
    "CUSTOMER.DISPUTE.RESOLVED",
}

DisputeLookup = Callable[[str], dict | None]


class SignatureError(Exception):
    pass


class WebhookNotConfigured(Exception):
    pass


def verify_and_parse(payload: bytes, headers: dict[str, str | None], client: PayPalClient) -> dict:
    """Verify with PayPal's verify-webhook-signature API, then parse.

    The only way to skip verification is PAYPAL_VERIFY_WEBHOOKS=0 together with DEMO_TOOLS=1,
    which exists so recorded fixtures can drive the demo. Never enable it anywhere real.
    """
    if not settings.paypal_verify_webhooks:
        if not settings.demo_tools:
            raise WebhookNotConfigured(
                "webhook verification can only be disabled with DEMO_TOOLS=1"
            )
    else:
        if not settings.paypal_webhook_id:
            raise WebhookNotConfigured("PAYPAL_WEBHOOK_ID is not set")
        try:
            ok = client.verify_webhook({k.lower(): v for k, v in headers.items()}, payload)
        except (PayPalError, UnicodeDecodeError) as exc:
            raise SignatureError(str(exc)) from exc
        if not ok:
            raise SignatureError("PayPal reported the signature as not verified")
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise SignatureError("body is not JSON") from exc


def fetch_dispute(dispute_id: str) -> dict | None:
    """Full dispute record for enrichment (webhook resources can be partial). Network call."""
    client = PayPalClient()
    if not client.available()[0]:
        return None
    try:
        return client.get_dispute(dispute_id)
    except PayPalError:
        log.warning("dispute lookup failed for %s", dispute_id, exc_info=True)
        return None


def _txn(resource: dict) -> dict:
    return (resource.get("disputed_transactions") or [{}])[0]


def _identifier(txn: dict) -> str | None:
    buyer = txn.get("buyer") or {}
    return buyer.get("email") or buyer.get("payer_id") or buyer.get("name")


def safe_classify(reason: str) -> tuple[str | None, str | None, bool]:
    try:
        result = classify("paypal", reason)
        return result.category, result.explanation, result.needs_review
    except Exception:
        log.warning("classify failed for reason %r", reason, exc_info=True)
        return None, None, True


def _meta(resource: dict) -> dict:
    return {
        "life_cycle_stage": resource.get("dispute_life_cycle_stage"),
        "channel": resource.get("dispute_channel"),
        "outcome_code": (resource.get("dispute_outcome") or {}).get("outcome_code"),
    }


def handle_event(
    session: Session,
    event: dict,
    dispute_lookup: DisputeLookup = fetch_dispute,
    collector: EvidenceCollector | None = None,
) -> str:
    """Apply one verified event. Returns a short outcome label (for logs and tests)."""
    event_id, event_type = event["id"], event["event_type"]
    if event_type not in HANDLED_EVENTS:
        return "ignored"
    if session.get(PayPalEventRow, event_id):
        return "duplicate"

    resource = event["resource"]
    dispute_id = resource["dispute_id"]
    event_at = mapping.parse_ts(event.get("create_time")) or datetime.now(UTC)
    row = session.query(DisputeRow).filter_by(processor_dispute_id=dispute_id).one_or_none()

    if row is not None and row.last_event_at and event_at < row.last_event_at:
        outcome = "stale"
    elif row is None:
        row = _create(session, resource, event_at, dispute_lookup, collector or default_collector())
        outcome = "created"
    else:
        _update(row, resource, event_at)
        outcome = "updated"

    session.add(PayPalEventRow(event_id=event_id, type=event_type, event_created_at=event_at))
    session.commit()
    return outcome


def _create(
    session: Session,
    resource: dict,
    event_at: datetime,
    dispute_lookup: DisputeLookup,
    collector: EvidenceCollector,
) -> DisputeRow:
    try:  # best-effort: prefer the full record, fall back to what the webhook carried
        full = dispute_lookup(resource["dispute_id"]) or {}
    except Exception:
        log.warning("dispute lookup raised for %s", resource["dispute_id"], exc_info=True)
        full = {}
    merged = {**resource, **full}
    txn = _txn(merged)
    seller_txn = txn.get("seller_transaction_id")
    seller = txn.get("seller") or {}
    seller_id = _resolve_seller(session, seller.get("merchant_id"))

    amount_obj = merged.get("dispute_amount") or txn.get("gross_amount") or {}
    currency = (amount_obj.get("currency_code") or "USD").lower()
    reason = merged.get("reason") or "OTHER"
    category, explanation, needs_review = safe_classify(reason)
    created_at = mapping.parse_ts(merged.get("create_time")) or event_at
    due = mapping.parse_ts(merged.get("seller_response_due_date"))
    status = mapping.map_dispute_status(
        merged.get("status"), (merged.get("dispute_outcome") or {}).get("outcome_code")
    )
    ident = _identifier(txn) or seller_txn or merged["dispute_id"]
    order_ref = txn.get("invoice_number") or txn.get("custom")

    row = DisputeRow(
        id="dp_" + secrets.token_hex(6),
        seller_id=seller_id,
        processor="paypal",
        processor_dispute_id=merged["dispute_id"],
        processor_charge_id=seller_txn,
        processor_status=merged.get("status"),
        amount=mapping.to_minor(amount_obj.get("value", "0"), currency),
        currency=currency,
        reason_raw=reason,
        category=category,
        category_explanation=explanation,
        category_needs_review=needs_review,
        status=next_status(None, None) if status is None else status,
        created_at=created_at,
        deadline_at=due or created_at + FALLBACK_DEADLINE,
        customer_hash=customer_hash(seller_id, ident),
        order_id=order_ref,
        last_event_at=event_at,
        processor_meta=_meta(merged),
    )
    session.add(row)
    session.flush()
    collect_for_dispute(session, row, collector)  # never raises, never loses the dispute
    return row


def _update(row: DisputeRow, resource: dict, event_at: datetime) -> None:
    outcome = (resource.get("dispute_outcome") or {}).get("outcome_code")
    target = mapping.map_dispute_status(resource.get("status"), outcome)
    row.processor_status = resource.get("status") or row.processor_status
    if target is not None:
        row.status = _guard(row.status, target)
    amount = resource.get("dispute_amount")
    if amount and amount.get("value"):
        row.amount = mapping.to_minor(amount["value"], amount.get("currency_code", row.currency))
    due = mapping.parse_ts(resource.get("seller_response_due_date"))
    if due:
        row.deadline_at = due
    row.processor_meta = {
        **(row.processor_meta or {}),
        **{k: v for k, v in _meta(resource).items() if v},
    }
    row.last_event_at = event_at


def _guard(current: str, target: str) -> str:
    """Reuse the Stripe rules for not regressing the seller's own workflow."""
    return next_status(current, _STATUS_ALIAS.get(target, target)) or current


# next_status() speaks Stripe statuses; map ours onto the equivalent so its guards apply.
_STATUS_ALIAS = {
    "needs_response": "needs_response",
    "submitted": "under_review",
    "won": "won",
    "lost": "lost",
    "accepted": "accepted",
}
