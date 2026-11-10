"""Webhook -> mock shop -> evidence rows, including the ways collection can fail."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.collectors import CollectedItem, Collection
from app.core.router import get_charge_lookup, get_collector
from app.core.stripe_ingest import ChargeInfo
from app.main import app
from app.settings import settings

from .helpers import SECRET, make_event, send


@pytest.fixture
def client(session, monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    app.dependency_overrides[get_charge_lookup] = lambda: lambda charge_id: ChargeInfo()
    yield TestClient(app)
    app.dependency_overrides.clear()


def only_dispute(client) -> dict:
    [d] = client.get("/core/disputes").json()
    return d


def test_new_dispute_is_populated_from_the_mock_shop(client) -> None:
    resp = send(client, make_event(order_id="ord_101"))
    assert resp.json()["outcome"] == "created"

    d = only_dispute(client)
    detail = client.get(f"/core/disputes/{d['id']}").json()
    evidence = detail["evidence"]
    assert {e["type"] for e in evidence} == {
        "order_receipt",
        "tracking",
        "delivery_proof",
        "ip_device",
        "refund_policy",
        "prior_orders",
    }
    assert all(e["verified"] for e in evidence)
    assert {e["source"] for e in evidence} <= {"shop_api", "shipping_api"}
    assert set(d["evidence"]) == {e["id"] for e in evidence}
    assert (d["order_id"], d["product_sku"], d["courier"]) == ("ord_101", "SKU-TEE-04", "CourierX")


def test_dispute_is_matched_by_customer_when_no_order_id(client) -> None:
    send(client, make_event(amount=12900, email="alex@example.com"))
    d = only_dispute(client)
    assert d["order_id"] == "ord_102"
    types = {e["type"] for e in client.get(f"/core/disputes/{d['id']}").json()["evidence"]}
    assert "customer_message" in types


def test_stored_evidence_has_no_raw_personal_data(client) -> None:
    send(client, make_event(amount=12900, email="alex@example.com"))
    d = only_dispute(client)
    for e in client.get(f"/core/disputes/{d['id']}").json()["evidence"]:
        assert "@" not in e["summary"]
    assert "alex@example.com" not in str(d)


def test_unknown_order_attaches_nothing_but_keeps_the_dispute(client) -> None:
    resp = send(client, make_event(order_id="ord_999", email="buyer@example.com"))
    assert resp.status_code == 200
    d = only_dispute(client)
    assert d["evidence"] == []
    assert d["order_id"] == "ord_999"


def test_undelivered_order_has_no_delivery_proof_in_db(client) -> None:
    send(client, make_event(order_id="ord_103", amount=8400))
    d = only_dispute(client)
    types = {e["type"] for e in client.get(f"/core/disputes/{d['id']}").json()["evidence"]}
    assert "delivery_proof" not in types
    assert "tracking" in types


class Exploding:
    def collect(self, ctx):
        raise RuntimeError("shop is down")


class PartiallyInvalid:
    """One valid item, then one the database must reject (a seller note marked as system data)."""

    def collect(self, ctx):
        at = datetime(2026, 9, 1, tzinfo=UTC)
        return Collection(
            items=[
                CollectedItem("order_receipt", "shop_api", "ok", "A valid receipt", at),
                CollectedItem("seller_note", "seller_claim", "bad", "must not be verified", at),
            ],
            order_id="ord_x",
        )


@pytest.mark.parametrize("collector", [Exploding(), PartiallyInvalid()], ids=["raises", "bad-row"])
def test_collection_failure_never_loses_the_dispute_or_leaves_partial_evidence(
    client, collector
) -> None:
    app.dependency_overrides[get_collector] = lambda: collector
    resp = send(client, make_event(order_id="ord_101"))
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "created"

    d = only_dispute(client)
    assert d["evidence"] == []  # the savepoint rolled back the whole batch
    assert d["order_id"] == "ord_101"  # from Stripe metadata, not from the failed collection


def test_collect_endpoint_is_idempotent(client) -> None:
    send(client, make_event(order_id="ord_101"))
    d = only_dispute(client)
    first = client.get(f"/core/disputes/{d['id']}").json()["evidence"]

    again = client.post(f"/core/disputes/{d['id']}/collect")
    again2 = client.post(f"/core/disputes/{d['id']}/collect")
    assert again.status_code == 200
    ids = lambda items: sorted(e["id"] for e in items)  # noqa: E731
    assert ids(again.json()["evidence"]) == ids(first) == ids(again2.json()["evidence"])
    assert len(first) == 6


def test_collect_endpoint_unknown_dispute(client) -> None:
    resp = client.post("/core/disputes/dp_nope/collect")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"
