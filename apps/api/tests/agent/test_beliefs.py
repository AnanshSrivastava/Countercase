# ruff: noqa: E501
import json
from datetime import date

from fastapi.testclient import TestClient

from app.agent import beliefs, seed_loader
from app.agent.beliefs import compute_beliefs, load_cases, propose_directives, record_outcome
from app.agent.memory import InMemoryStore
from app.main import app

HISTORY = json.loads(seed_loader.HISTORY.read_text(encoding="utf-8"))


def seeded() -> InMemoryStore:
    store = InMemoryStore()
    seed_loader.load(store, HISTORY)
    return store


def test_planted_patterns_become_beliefs_with_honest_labels():
    bs = {b.key: b for b in compute_beliefs(load_cases(seeded(), "sel_demo"))}
    photo = bs["evidence:not_received"]
    assert (
        "Delivery photo" in photo.text
        and photo.confidence > 0.9
        and photo.label in {"moderate", "strong"}
    )
    assert bs["courier:CourierX"].kind == "courier"


def test_no_belief_below_minimum_cases():
    store = InMemoryStore()
    store.retain(
        "s",
        "Won",
        kind="case",
        event_date=date(2026, 8, 1),
        tags=["reason:not_received", "outcome:won", "evidence:delivery_photo"],
    )
    assert compute_beliefs(load_cases(store, "s")) == []


def test_recording_an_outcome_reports_confidence_change():
    store = InMemoryStore()
    seed_loader.load(store, HISTORY, limit=14)  # sparse history first
    dispute = {
        "id": "dp_x",
        "seller_id": "sel_demo",
        "category": "not_received",
        "courier": "CourierY",
        "product_sku": "SKU-MUG-01",
        "customer_hash": "c_new",
    }
    beliefs.CHANGE_LOG.clear()
    for n in range(4):  # four different disputes, each reported once
        record_outcome(
            store,
            {**dispute, "id": f"dp_x{n}"},
            {"order_receipt", "delivery_proof"},
            "won",
            date(2026, 10, 5),
        )
    changes = [c for c in beliefs.CHANGE_LOG if c["key"] == "evidence:not_received"]
    assert (
        changes and changes[-1]["after"] >= changes[0]["after"]
    )  # more wins with the photo -> not less confident
    assert all("before" in c and "after" in c for c in changes)


def test_edit_proposals_are_proposals_only():
    props = propose_directives(
        "Dear team, here is the proof.", "Dear team, per our return policy, here is the proof."
    )
    assert any("return policy" in p["text"] for p in props)
    assert propose_directives("x" * 100, "x" * 40)[0]["text"] == "Keep letters short and formal"
    assert propose_directives("a", "a", "accept", 3000)[0]["text"].startswith(
        "Never fight disputes under"
    )


def test_playbook_and_dismissal_via_api():
    from app.agent.router import get_store

    get_store.cache_clear()
    seed_loader.load(get_store(), HISTORY)
    client = TestClient(app)
    pb = client.get("/agent/playbook").json()
    assert pb["best_evidence"] and "# Seller Playbook" in pb["markdown"] and pb["preferences"]
    key = pb["best_evidence"][0]["key"]
    client.delete(f"/agent/beliefs/{key}")
    assert key not in {b["key"] for b in client.get("/agent/beliefs").json()}
    props = client.post(
        "/agent/disputes/dp_001/edit", json={"before": "a" * 100, "after": "a" * 30}
    ).json()["proposals"]
    assert props
    beliefs.DISMISSED.clear()
    get_store.cache_clear()


def test_reporting_the_same_outcome_twice_counts_once():
    store = InMemoryStore()
    dispute = {
        "id": "dp_dup",
        "seller_id": "s",
        "category": "not_received",
        "courier": "CourierX",
        "product_sku": "SKU-1",
        "customer_hash": "c_1",
    }
    record_outcome(store, dispute, {"delivery_proof"}, "won", date(2026, 10, 5))
    second = record_outcome(store, dispute, {"delivery_proof"}, "won", date(2026, 10, 5))
    assert len(load_cases(store, "s")) == 1
    assert second == []  # nothing new learned the second time
