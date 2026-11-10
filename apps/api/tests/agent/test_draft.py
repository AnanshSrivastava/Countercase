# ruff: noqa: E501
import json
from datetime import date
from pathlib import Path

from app.agent.draft import build_draft
from app.agent.memory import InMemoryStore

FIX = Path(__file__).resolve().parents[4] / "fixtures" / "disputes"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def seeded_store(seller):
    s = InMemoryStore()
    for d in (date(2026, 7, 1), date(2026, 8, 14)):
        s.retain(
            seller,
            "Won not_received with delivery photo",
            kind="case",
            event_date=d,
            tags=[
                "reason:not_received",
                "courier:CourierX",
                "outcome:won",
                "evidence:delivery_photo",
            ],
        )
    s.retain(
        seller,
        "Lost not_received, no proof",
        kind="case",
        event_date=date(2026, 6, 1),
        tags=["reason:not_received", "outcome:lost"],
    )
    s.set_directive(seller, "Always cite the 7-day return policy")
    return s


def test_memory_on_uses_history_and_off_does_not():
    data = load("dp_001_not_received.json")
    d, ev = data["dispute"], data["evidence"]
    store = seeded_store(d["seller_id"])
    off = build_draft(d, ev, store, memory_on=False)
    on = build_draft(d, ev, store, memory_on=True)
    assert off["memory"] == [] and off["advice"]["n_cases"] == 0
    assert (
        on["advice"]["n_cases"] == 2  # same reason AND delivery photo: 2 wins
        and on["advice"]["win_probability"] > off["advice"]["win_probability"]
    )
    assert any(m["kind"] == "directive" for m in on["memory"])
    assert on["claims"] == off["claims"]  # same evidence, same claims: only advice/memory differ


def test_all_claims_are_sourced_and_seller_note_never_cited():
    data = load("dp_001_not_received.json")
    draft = build_draft(data["dispute"], data["evidence"], InMemoryStore(), memory_on=False)
    verified = {e["id"] for e in data["evidence"] if e["verified"]}
    assert draft["claims"] and all(c["evidence_id"] in verified for c in draft["claims"])
    assert "neighbour" not in draft["letter_md"]


def test_bad_generator_output_is_rejected():
    data = load("dp_001_not_received.json")

    def gen(d, e, m):
        return [{"text": "Customer signed personally.", "evidence_id": "ev_404"}]

    draft = build_draft(
        data["dispute"], data["evidence"], InMemoryStore(), memory_on=False, generate_claims=gen
    )
    assert draft["claims"] == [] and len(draft["rejected_claims"]) == 1 and draft["letter_md"] == ""


def test_min_amount_directive_triggers_accept():
    data = load("dp_001_not_received.json")
    store = InMemoryStore()
    store.set_directive(data["dispute"]["seller_id"], "Never fight disputes under 500")
    assert (
        build_draft(data["dispute"], data["evidence"], store, memory_on=True)["advice"]["action"]
        == "accept"
    )  # 129.00 is under the 500 minimum


def test_returned_parcel_without_delivery_proof_is_accepted_with_no_rebuttal():
    dispute = {
        "id": "dp_r",
        "seller_id": "s",
        "category": "not_received",
        "amount": 8400,
        "currency": "usd",
        "courier": "CourierZ",
        "product_sku": "SKU-BAG-07",
        "customer_hash": "c_r",
    }
    evidence = [
        {
            "id": "ev_a",
            "type": "order_receipt",
            "verified": True,
            "summary": "Order ord_103",
            "source": "shop_api",
        },
        {
            "id": "ev_b",
            "type": "tracking",
            "verified": True,
            "summary": "Shipped, attempt failed, returned to sender",
            "source": "shipping_api",
        },
    ]
    for mode in (False, True):
        draft = build_draft(dispute, evidence, InMemoryStore(), memory_on=mode)
        assert (
            draft["advice"]["action"] == "accept"
            and draft["claims"] == []
            and draft["letter_md"] == ""
        )
        assert "appears valid" in " ".join(draft["advice"]["rationale"])


def test_damaged_item_covered_by_own_policy_is_accepted():
    data = load("dp_003_not_as_described.json")
    for mode in (False, True):
        draft = build_draft(data["dispute"], data["evidence"], InMemoryStore(), memory_on=mode)
        assert draft["advice"]["action"] == "accept" and draft["claims"] == []
