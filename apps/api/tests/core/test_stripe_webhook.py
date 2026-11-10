import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core import stripe_ingest
from app.core.router import get_charge_lookup
from app.core.stripe_ingest import ChargeInfo, next_status
from app.main import app
from app.settings import settings

SECRET = "whsec_test_secret"
DUE_BY = 1_791_590_399


@pytest.fixture
def client(session, monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    app.dependency_overrides[get_charge_lookup] = lambda: (
        lambda charge_id: ChargeInfo(identifier="Jane@Example.com", metadata={"order_id": "ord_99"})
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def event(event_id, kind, *, status="needs_response", created=1_791_000_000, due_by=DUE_BY):
    dispute = {
        "id": "du_test_abc",
        "object": "dispute",
        "amount": 12900,
        "currency": "usd",
        "charge": "ch_test_1",
        "reason": "product_not_received",
        "status": status,
        "created": 1_790_990_000,
        "evidence": {"customer_email_address": None},
        "evidence_details": {"due_by": due_by},
        "metadata": {},
    }
    return {"id": event_id, "type": kind, "created": created, "data": {"object": dispute}}


def send(client, payload, secret=SECRET):
    body = json.dumps(payload)
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return client.post(
        "/core/webhooks/stripe",
        content=body,
        headers={"Stripe-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"},
    )


def test_created_event_makes_classified_dispute(client) -> None:
    resp = send(client, event("evt_1", "charge.dispute.created"))
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "created"

    [d] = client.get("/core/disputes").json()
    assert d["processor_dispute_id"] == "du_test_abc"
    assert d["category"] == "not_received"  # filled by app.agent.classifier
    assert d["category_explanation"]  # v0.2: classifier explanation is exposed
    assert d["status"] == "needs_response"
    assert d["order_id"] == "ord_99"
    assert datetime.fromisoformat(d["deadline_at"]) == datetime.fromtimestamp(DUE_BY, tz=UTC)
    assert d["customer_hash"].startswith("c_")


def test_customer_hash_is_per_seller_and_normalized() -> None:
    from app.core.hashing import customer_hash

    assert customer_hash("s1", " Jane@Example.com ") == customer_hash("s1", "jane@example.com")
    assert customer_hash("s1", "jane@example.com") != customer_hash("s2", "jane@example.com")


def test_bad_signature_rejected(client) -> None:
    resp = send(client, event("evt_1", "charge.dispute.created"), secret="whsec_wrong")
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_signature"
    assert client.get("/core/disputes").json() == []


def test_unconfigured_secret_rejects_everything(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    resp = send(client, event("evt_1", "charge.dispute.created"))
    assert resp.status_code == 503
    assert resp.json()["error"] == "webhook_not_configured"


def test_duplicate_event_is_ignored(client) -> None:
    send(client, event("evt_1", "charge.dispute.created"))
    resp = send(client, event("evt_1", "charge.dispute.created"))
    assert resp.json()["outcome"] == "duplicate"
    assert len(client.get("/core/disputes").json()) == 1


def test_update_before_create_still_creates(client) -> None:
    assert send(client, event("evt_2", "charge.dispute.updated")).json()["outcome"] == "created"
    late_create = event("evt_1", "charge.dispute.created", created=1_790_999_000)
    assert send(client, late_create).json()["outcome"] == "stale"
    assert len(client.get("/core/disputes").json()) == 1


def test_update_without_due_by_keeps_deadline_then_closes(client) -> None:
    send(client, event("evt_1", "charge.dispute.created"))
    update = event(
        "evt_2", "charge.dispute.updated", status="under_review", created=1_791_000_100, due_by=None
    )
    send(client, update)
    [d] = client.get("/core/disputes").json()
    assert d["status"] == "submitted"
    assert datetime.fromisoformat(d["deadline_at"]) == datetime.fromtimestamp(DUE_BY, tz=UTC)

    send(client, event("evt_3", "charge.dispute.closed", status="won", created=1_791_000_200))
    assert client.get("/core/disputes").json()[0]["status"] == "won"


def test_other_event_types_ignored(client) -> None:
    payload = {"id": "evt_x", "type": "charge.succeeded", "created": 1, "data": {"object": {}}}
    assert send(client, payload).json()["outcome"] == "ignored"


@pytest.mark.parametrize(
    ("current", "stripe_status", "expected"),
    [
        (None, "needs_response", "needs_response"),
        (None, "warning_needs_response", "needs_response"),
        ("drafted", "needs_response", "drafted"),
        ("approved", "needs_response", "approved"),
        ("approved", "under_review", "submitted"),
        ("accepted", "lost", "accepted"),
        ("submitted", "lost", "lost"),
        ("won", "needs_response", "won"),
        ("drafted", "something_new", "drafted"),
    ],
)
def test_status_mapping(current, stripe_status, expected) -> None:
    assert next_status(current, stripe_status) == expected


def test_charge_lookup_skipped_without_real_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_xxx")
    assert stripe_ingest.fetch_charge_info("ch_1") == ChargeInfo()


def test_missing_signature_header_rejected(client) -> None:
    body = json.dumps(event("evt_1", "charge.dispute.created"))
    resp = client.post("/core/webhooks/stripe", content=body)
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_signature"


def test_lookup_failure_still_creates_dispute(client) -> None:
    def boom(charge_id):
        raise RuntimeError("stripe down")

    app.dependency_overrides[get_charge_lookup] = lambda: boom
    assert send(client, event("evt_1", "charge.dispute.created")).json()["outcome"] == "created"
    [d] = client.get("/core/disputes").json()
    assert d["category"] == "not_received"
    assert d["order_id"] is None


def test_classifier_failure_still_creates_dispute(client, monkeypatch) -> None:
    def boom(processor, reason):
        raise RuntimeError("classifier broke")

    monkeypatch.setattr(stripe_ingest, "classify", boom)
    assert send(client, event("evt_1", "charge.dispute.created")).json()["outcome"] == "created"
    [d] = client.get("/core/disputes").json()
    assert d["category"] is None


def test_charge_lookup_reads_real_stripe_object(monkeypatch) -> None:
    import stripe

    charge = stripe.StripeObject.construct_from(
        {
            "id": "ch_1",
            "billing_details": {"email": "a@b.c"},
            "customer": "cus_1",
            "metadata": {"order_id": "ord_7"},
        },
        "sk_test_k",
    )

    class FakeCharges:
        def retrieve(self, charge_id):
            return charge

    class FakeClient:
        def __init__(self, key):
            self.charges = FakeCharges()

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_real")
    monkeypatch.setattr(stripe, "StripeClient", FakeClient)
    assert stripe_ingest.fetch_charge_info("ch_1") == ChargeInfo("a@b.c", {"order_id": "ord_7"})
