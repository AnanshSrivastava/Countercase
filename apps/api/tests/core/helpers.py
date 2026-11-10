"""Shared helpers for core tests: signed Stripe events."""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

SECRET = "whsec_test_secret"
DISPUTE_CREATED_AT = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def make_event(
    event_id: str = "evt_1",
    *,
    kind: str = "charge.dispute.created",
    dispute_id: str = "du_ev_1",
    amount: int = 4999,
    currency: str = "usd",
    reason: str = "product_not_received",
    status: str = "needs_response",
    order_id: str | None = None,
    email: str | None = None,
) -> dict:
    created = int(DISPUTE_CREATED_AT.timestamp())
    dispute = {
        "id": dispute_id,
        "object": "dispute",
        "amount": amount,
        "currency": currency,
        "charge": "ch_test_1",
        "reason": reason,
        "status": status,
        "created": created,
        "evidence": {"customer_email_address": email},
        "evidence_details": {"due_by": created + 7 * 86400},
        "metadata": {"order_id": order_id} if order_id else {},
    }
    return {"id": event_id, "type": kind, "created": created, "data": {"object": dispute}}


def send(client, payload: dict, secret: str = SECRET):
    body = json.dumps(payload)
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return client.post(
        "/core/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"},
    )
