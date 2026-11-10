"""GET /core/insights (real Postgres, through the real app)."""

from datetime import UTC, datetime, timedelta
from itertools import count

import pytest
from fastapi.testclient import TestClient

from app.core.disputes import ensure_seller
from app.core.tables import DisputeRow, EvidenceRow
from app.main import app

client = TestClient(app)
_ids = count(1)
T0 = datetime(2026, 9, 1, tzinfo=UTC)


def add(
    session,
    status,
    *,
    amount=1000,
    category="not_received",
    courier=None,
    sku=None,
    currency="usd",
    seller="sel_demo",
    evidence=(),
):
    """One dispute; `evidence` is a list of types (verified, shop_api) or (type, verified)."""
    ensure_seller(session, seller)
    n = next(_ids)
    did = f"t_{n}"
    session.add(
        DisputeRow(
            id=did,
            seller_id=seller,
            processor="stripe",
            processor_dispute_id=f"du_{did}",
            amount=amount,
            currency=currency,
            reason_raw="x",
            category=category,
            status=status,
            created_at=T0,
            deadline_at=T0 + timedelta(days=7),
            customer_hash=f"c_{n}",
            product_sku=sku,
            courier=courier,
        )
    )
    session.flush()
    for i, ev in enumerate(evidence):
        etype, verified = (ev, True) if isinstance(ev, str) else ev
        session.add(
            EvidenceRow(
                id=f"ev_{did}_{i}",
                dispute_id=did,
                type=etype,
                source="shop_api",
                verified=verified,
                summary="x",
                captured_at=T0,
            )
        )
    session.commit()
    return did


def get(**params):
    resp = client.get("/core/insights", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def tip_ids(body):
    return [t["id"] for t in body["tips"]]


def test_empty_database_returns_zeros_not_errors(session) -> None:
    body = get()
    h = body["headline"]
    assert h["total_disputes"] == 0 and h["open_disputes"] == 0 and h["fought"] == 0
    assert h["win_rate"] is None and h["net_recovery_rate"] is None
    assert h["money_at_stake_open"] == h["money_lost"] == h["money_recovered"] == 0
    assert body["top_reasons"] == [] and body["win_rate_by_category"] == []
    assert body["worst_couriers"] == [] and body["worst_products"] == [] and body["tips"] == []
    assert all(r["won_with"] == 0 and r["won_total"] == 0 for r in body["evidence_readiness"])
    assert body["currency"] == "usd" and body["other_currencies"] == []


def test_headline_math(session) -> None:
    for _ in range(3):
        add(session, "won", amount=1000)
    add(session, "lost", amount=2000)
    add(session, "accepted", amount=500)
    add(session, "needs_response", amount=700)
    add(session, "submitted", amount=300)
    h = get()["headline"]
    assert (h["total_disputes"], h["open_disputes"], h["closed_disputes"]) == (7, 2, 5)
    assert (h["won"], h["lost"], h["accepted"], h["fought"]) == (3, 1, 1, 4)
    assert h["win_rate"] == 0.75  # accepted is not fought
    assert h["money_at_stake_open"] == 1000
    assert (h["money_lost"], h["money_conceded"], h["money_recovered"]) == (2000, 500, 3000)
    assert h["total_disputed_amount"] == 6500
    assert h["net_recovery_rate"] == pytest.approx(3000 / 6500, abs=1e-4)
    assert h["net_recovery_rate_closed"] == pytest.approx(3000 / 5500, abs=1e-4)


def test_only_one_currency_is_counted_and_others_reported(session) -> None:
    add(session, "won", amount=1000)
    add(session, "lost", amount=1000)
    add(session, "lost", amount=999_999, currency="eur")
    body = get()
    assert body["currency"] == "usd"
    assert body["other_currencies"] == [{"currency": "eur", "disputes": 1}]
    assert body["headline"]["total_disputes"] == 2
    assert body["headline"]["money_lost"] == 1000


def test_per_seller_isolation(session) -> None:
    add(session, "won", amount=1000)
    add(session, "lost", amount=5000, seller="sel_other")
    assert get()["headline"]["total_disputes"] == 1
    assert get(seller_id="sel_other")["headline"]["money_lost"] == 5000


def test_top_reasons_and_category_win_rate_with_low_confidence(session) -> None:
    for _ in range(3):
        add(session, "won", category="not_received", amount=100)
    add(session, "lost", category="not_received", amount=100)
    add(session, "lost", category="unauthorized", amount=900)
    add(session, "needs_response", category="unauthorized", amount=100)
    body = get()
    assert body["top_reasons"][0] == {"category": "not_received", "count": 4, "amount": 400}
    assert body["top_reasons"][1] == {"category": "unauthorized", "count": 2, "amount": 1000}
    cats = {c["category"]: c for c in body["win_rate_by_category"]}
    assert cats["not_received"]["win_rate"] == 0.75
    assert cats["not_received"]["n_fought"] == 4 and not cats["not_received"]["low_confidence"]
    assert cats["unauthorized"]["win_rate"] == 0.0 and cats["unauthorized"]["n_closed"] == 1
    assert cats["unauthorized"]["low_confidence"] is True


def test_courier_and_product_ranking_and_small_samples(session) -> None:
    for _ in range(3):
        add(session, "lost", amount=1000, courier="CourierX", sku="A")
    add(session, "won", courier="CourierX", sku="A")
    add(session, "lost", amount=5000, courier="CourierY", sku="B")
    add(session, "won", courier="CourierY", sku="B")
    add(session, "lost", amount=9000, courier="CourierZ", sku="C")  # n_closed = 1: not ranked
    add(session, "won", courier="CourierW", sku="D")  # no losses: not "worst"
    add(session, "won", courier="CourierW", sku="D")
    body = get()
    couriers = body["worst_couriers"]
    assert [c["key"] for c in couriers] == ["CourierY", "CourierX"]  # by money lost
    x = couriers[1]
    assert (x["lost"], x["n_fought"], x["loss_rate"], x["money_lost"]) == (3, 4, 0.75, 3000)
    assert x["small_sample"] is True and couriers[0]["small_sample"] is True
    assert [p["key"] for p in body["worst_products"]] == ["B", "A"]


def test_courier_tip_fires_and_does_not_fire(session) -> None:
    for _ in range(3):
        add(session, "lost", courier="CourierX")
    add(session, "won", courier="CourierX")
    add(session, "lost", courier="CourierY")
    for _ in range(5):
        add(session, "won", courier="CourierY")
    body = get()
    tip = next(t for t in body["tips"] if t["id"] == "courier_loss_rate")
    assert "CourierX" in tip["title"]
    assert tip["small_sample"] is True and "Small sample" in tip["sample_note"]
    assert any("3 lost of 4" in f["value"] for f in tip["evidence"])


def test_courier_tip_absent_when_couriers_are_alike(session) -> None:
    for courier in ("CourierX", "CourierY"):
        add(session, "lost", courier=courier)
        add(session, "lost", courier=courier)
        add(session, "won", courier=courier)
        add(session, "won", courier=courier)
    assert "courier_loss_rate" not in tip_ids(get())


def test_category_tip_names_the_missing_evidence_type(session) -> None:
    for _ in range(5):
        add(session, "won", category="not_received")
    add(session, "won", category="unauthorized", evidence=["prior_orders"])
    add(session, "lost", category="unauthorized")
    add(session, "lost", category="unauthorized")
    tip = next(t for t in get()["tips"] if t["id"] == "category_low_win_rate")
    assert "unauthorized" in tip["title"]
    assert any(
        "prior orders" in f["label"] and "1 of 1 won vs 0 of 2" in f["value"]
        for f in tip["evidence"]
    )
    assert "prior orders" in tip["action"]


def test_category_tip_absent_for_tiny_category(session) -> None:
    for _ in range(5):
        add(session, "won", category="not_received")
    add(session, "lost", category="unauthorized")
    add(session, "lost", category="unauthorized")  # only 2 fought: below the minimum
    assert "category_low_win_rate" not in tip_ids(get())


def test_product_concentration_tip(session) -> None:
    for _ in range(4):
        add(session, "needs_response", sku="SKU-HOT", category="other")
    for i in range(6):
        add(session, "needs_response", sku=f"SKU-{i}", category="other")
    tip = next(t for t in get()["tips"] if t["id"] == "product_concentration")
    assert "SKU-HOT" in tip["title"] and tip["evidence"][0]["value"].startswith("4 of 10")
    assert tip["small_sample"] is True


def test_product_concentration_absent_when_spread_out(session) -> None:
    for i in range(10):
        add(session, "needs_response", sku=f"SKU-{i % 5}", category="other")
    assert "product_concentration" not in tip_ids(get())


def _large_dataset(session, big_has_proof: bool) -> None:
    for _ in range(6):
        add(session, "won", amount=1000, evidence=["delivery_proof"])
    for _ in range(2):
        ev = ["delivery_proof"] if big_has_proof else ["tracking"]
        add(session, "lost", amount=9000, evidence=ev)


def test_large_amount_without_delivery_proof_tip(session) -> None:
    _large_dataset(session, big_has_proof=False)
    tip = next(t for t in get()["tips"] if t["id"] == "large_without_delivery_proof")
    assert any(f["label"].startswith("...without") and f["value"] == "2" for f in tip["evidence"])


def test_large_amount_tip_absent_when_proof_exists(session) -> None:
    _large_dataset(session, big_has_proof=True)
    assert "large_without_delivery_proof" not in tip_ids(get())


def test_evidence_gap_tip_and_readiness_counts_only_verified(session) -> None:
    for _ in range(3):
        add(session, "won", evidence=["delivery_proof", "order_receipt"])
    # Unverified delivery_proof (shop_api, verified=false) must not count for the lost cases.
    for _ in range(3):
        add(session, "lost", evidence=[("delivery_proof", False), "order_receipt"])
    add(session, "lost", evidence=["delivery_proof", "delivery_proof"])  # one pair, counted once
    body = get()
    rd = {r["type"]: r for r in body["evidence_readiness"]}
    assert (rd["delivery_proof"]["won_with"], rd["delivery_proof"]["won_total"]) == (3, 3)
    assert (rd["delivery_proof"]["lost_with"], rd["delivery_proof"]["lost_total"]) == (1, 4)
    assert rd["order_receipt"]["lost_with"] == 3
    assert "seller_note" not in rd and "seller_upload" not in rd
    tip = next(t for t in body["tips"] if t["id"] == "evidence_gap")
    assert {f["value"] for f in tip["evidence"]} == {"3 of 3", "1 of 4"}


def test_evidence_gap_tip_absent_when_present_equally(session) -> None:
    for status in ("won", "lost"):
        for _ in range(3):
            add(session, status, evidence=["delivery_proof"])
    assert "evidence_gap" not in tip_ids(get())


def test_no_tips_when_data_does_not_support_any(session) -> None:
    add(session, "won")
    add(session, "lost")
    assert get()["tips"] == []


def test_tips_are_capped_and_never_invented(session) -> None:
    for _ in range(3):
        add(session, "lost", courier="CourierX", sku="HOT", evidence=["tracking"])
    for _ in range(5):
        add(session, "won", courier="CourierY", sku="HOT", evidence=["delivery_proof"])
    body = get()
    assert 1 <= len(body["tips"]) <= 5
    for t in body["tips"]:
        assert t["evidence"] and t["action"]


def test_synthetic_demo_history_gives_meaningful_insights(session) -> None:
    """Shivansh's seed (make seed-core) feeds the dashboard: 62 closed cases, no open ones."""
    import json

    from app.agent import seed_core

    seed_core.seed_history(session, json.loads(seed_core.HISTORY.read_text(encoding="utf-8")))
    body = get()
    h = body["headline"]
    assert (h["total_disputes"], h["won"], h["lost"], h["accepted"]) == (62, 28, 30, 4)
    assert h["open_disputes"] == 0 and h["money_at_stake_open"] == 0
    # About $2,820 lost, $2,530 won, $338 accepted (includes the planted live repeat-customer case).
    assert (h["money_lost"], h["money_recovered"], h["money_conceded"]) == (282000, 253000, 33800)
    assert body["worst_couriers"] and body["tips"] and body["top_reasons"]
    rd = {r["type"]: r for r in body["evidence_readiness"]}
    assert rd["delivery_proof"]["won_with"] > rd["delivery_proof"]["lost_with"]
    assert rd["delivery_proof"]["won_total"] == 28 and rd["delivery_proof"]["lost_total"] == 30
