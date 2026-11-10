"""Synthetic dispute history for the demo seller (sel_demo). Deterministic: same seed -> same file.

ALL DATA IS SYNTHETIC. Outcomes come from a hidden ground-truth win model (`true_win_probability`) so that
(a) a memory-enabled agent can genuinely learn it, and (b) eval/ can compare memory on vs off on held-out cases.

Planted patterns the demo should surface:
- delivery photo wins 'not received' disputes
- from 2026-08-01 CourierX accounts for most losses
- customer c_9f2a71d0 disputed ord_31 in Aug and later confirmed receipt
- seller preferences (directives) and a few seller opinions (never treated as facts)

Run:  python data/seed/generate.py   ->  data/seed/history.json
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

SELLER = "sel_demo"
CREATE_UNTIL = date(2026, 9, 10)  # disputes are opened until here...
CUTOFF = date(2026, 9, 30)  # ...and every outcome is known before 30 Sep, so memory never knows the future
# of the demo disputes (fixtures dp_001..003 open on 1 Oct 2026)
START = date(2026, 3, 1)
COURIERS = ["CourierX", "CourierY", "CourierZ"]
SKUS = {"SKU-MUG-01": 12900, "SKU-TEE-04": 4900, "SKU-LAMP-02": 8900, "SKU-BAG-07": 15900, "SKU-CAP-03": 2500}
CATEGORIES = [("not_received", 0.45), ("unauthorized", 0.25), ("not_as_described", 0.15),
              ("refund_not_processed", 0.10), ("duplicate", 0.05)]
REPEAT_CUSTOMER = "c_9f2a71d0"  # customer of fixtures/disputes/dp_001
# Same story for the 129 USD dispute that `make demo-reset` creates through the webhook path: that
# customer's id is hash("ch_demo_1") for sel_demo with the default dev salt (CUSTOMER_HASH_SALT).
LIVE_REPEAT_CUSTOMER = "c_98a4e451561e529b"


def true_win_probability(category: str, evidence: list[str], courier: str, created: date) -> float:
    """Hidden ground truth. Never shown to the agent; used only to draw outcomes and to score eval."""
    p = {"not_received": 0.25, "unauthorized": 0.20, "not_as_described": 0.35,
         "refund_not_processed": 0.12, "duplicate": 0.60}[category]
    if category == "not_received":
        p += 0.50 if "delivery_photo" in evidence else 0.0
        p += 0.08 if "signature" in evidence else 0.0
        if courier == "CourierX" and created >= date(2026, 8, 1):
            p -= 0.30  # the planted bad-courier pattern
    if category == "unauthorized":
        p += 0.45 if "prior_orders" in evidence else 0.0
        p += 0.10 if "ip_device" in evidence else 0.0
    if category == "not_as_described" and "refund_policy" in evidence:
        p += 0.25
    return max(0.03, min(0.95, p))


def _evidence_for(rng: random.Random, category: str, courier: str) -> list[str]:
    ev = ["order_receipt"]
    if category == "not_received":
        ev.append("tracking")
        if rng.random() < 0.55:
            ev.append("delivery_photo")
        if rng.random() < 0.30:
            ev.append("signature")
    elif category == "unauthorized":
        if rng.random() < 0.55:
            ev.append("prior_orders")
        if rng.random() < 0.50:
            ev.append("ip_device")
    elif category == "not_as_described":
        if rng.random() < 0.60:
            ev.append("refund_policy")
    if rng.random() < 0.25:
        ev.append("customer_message")
    return ev


def build(seed: int = 7, n: int = 60) -> dict:
    rng = random.Random(seed)
    days = (CREATE_UNTIL - START).days
    recent_start = (date(2026, 8, 1) - START).days
    # 35% of disputes land after 1 Aug (volume grew), so the recent CourierX pattern has enough cases.
    created_dates = sorted(
        START + timedelta(days=rng.randrange(recent_start, days) if rng.random() < 0.35 else rng.randrange(recent_start))
        for _ in range(n)
    )
    cats = [c for c, _ in CATEGORIES]
    weights = [w for _, w in CATEGORIES]
    customers = [f"c_{rng.getrandbits(32):08x}" for _ in range(1500)]
    cases = []
    for i, created in enumerate(created_dates, start=1):
        category = rng.choices(cats, weights)[0]
        # CourierX handles more parcels after September, which is what makes it dominate recent losses.
        courier = rng.choices(COURIERS, [0.55, 0.25, 0.20] if created >= date(2026, 8, 1) else [0.34, 0.33, 0.33])[0]
        sku = rng.choice(list(SKUS))
        customer = rng.choice(customers)
        evidence = _evidence_for(rng, category, courier)
        p = true_win_probability(category, evidence, courier, created)
        # Obviously valid refund claims are mostly accepted rather than fought (honest advice).
        accepted = category == "refund_not_processed" and rng.random() < 0.6
        outcome = "accepted" if accepted else ("won" if rng.random() < p else "lost")
        resolved = min(created + timedelta(days=rng.randint(18, 40)), CUTOFF)
        cases.append({
            "id": f"hist_{i:03d}", "created": created.isoformat(), "resolved": resolved.isoformat(),
            "category": category, "courier": courier, "sku": sku, "amount": SKUS[sku], "currency": "usd",
            "customer": customer, "evidence": evidence, "outcome": outcome,
            "true_win_probability": round(p, 3), "holdout": False,
        })
    # Planted repeat-disputer story, 6 weeks before the first demo dispute (2026-10-01 -> ~2026-08-20).
    cases.append({
        "id": "hist_031x", "created": "2026-07-30", "resolved": "2026-08-20", "category": "not_received",
        "courier": "CourierX", "sku": "SKU-MUG-01", "amount": 12900, "currency": "usd", "customer": REPEAT_CUSTOMER,
        "evidence": ["order_receipt", "tracking"], "outcome": "lost", "true_win_probability": 0.25, "holdout": False,
        "note": "Customer later confirmed the parcel had been left with a neighbour.",
    })
    cases.sort(key=lambda c: c["created"])
    for c in rng.sample(cases, 12):  # held out for evaluation: memory is never given their outcomes
        c["holdout"] = True
    # Appended AFTER the random draws and the holdout sample, so it changes nothing else in the history.
    cases.append({
        "id": "hist_032x", "created": "2026-07-28", "resolved": "2026-08-18", "category": "not_received",
        "courier": "CourierX", "sku": "SKU-MUG-01", "amount": 12900, "currency": "usd",
        "customer": LIVE_REPEAT_CUSTOMER, "evidence": ["order_receipt", "tracking"], "outcome": "lost",
        "true_win_probability": 0.25, "holdout": False,
        "note": "Customer later confirmed the parcel had been left with a neighbour.",
    })
    cases.sort(key=lambda c: c["created"])
    return {
        "synthetic": True, "seller_id": SELLER, "seed": seed, "cases": cases,
        "directives": ["Always cite the 7-day return policy", "Never fight disputes under 20",
                       "Keep letters short and formal"],
        "opinions": ["Seller thinks CourierY is more reliable than CourierX (unverified)"],
    }


if __name__ == "__main__":
    out = Path(__file__).with_name("history.json")
    data = build()
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    c = data["cases"]
    print(f"wrote {out} - {len(c)} cases, {sum(x['holdout'] for x in c)} held out")
