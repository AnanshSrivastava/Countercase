"""Memory OFF vs ON on held-out synthetic disputes. SIMULATION on synthetic data (see data/seed/generate.py).

For each of N random seller histories: load every non-held-out case into memory, then for each held-out
case that was actually fought, ask the agent for advice with memory OFF (shared prior only) and ON
(this seller's history), and compare against the outcome that really happened in the simulation.

Metrics
- Brier score of the win probability (lower is better): is the number honest?
- Mean profit per fought dispute if the agent's advice is followed (fight: win +amount, lose -fee,
  both -effort; accept: 0). Compared with an oracle that knows the true win probability.
- Share of "accept" advice that was right (the fight would have lost).

Run:  python eval/run_eval.py [--sellers 40] > eval/results.md
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "apps" / "api"), str(ROOT / "data" / "seed")]

import generate
from app.agent import seed_loader
from app.agent.draft import build_draft
from app.agent.memory import InMemoryStore

FEE, EFFORT = 1500, 500
EVIDENCE_TYPE = {
    "delivery_photo": "delivery_proof",
    "tracking": "tracking",
    "order_receipt": "order_receipt",
    "prior_orders": "prior_orders",
    "ip_device": "ip_device",
    "refund_policy": "refund_policy",
    "customer_message": "customer_message",
    "signature": "delivery_proof",
}


def as_dispute(c: dict) -> tuple[dict, list[dict]]:
    dispute = {
        "id": c["id"],
        "seller_id": "sel_demo",
        "category": c["category"],
        "amount": c["amount"],
        "currency": c["currency"],
        "courier": c["courier"],
        "product_sku": c["sku"],
        "customer_hash": c["customer"],
    }
    types = sorted({EVIDENCE_TYPE[e] for e in c["evidence"]})
    evidence = [
        {
            "id": f"ev_{i}",
            "type": t,
            "verified": True,
            "summary": t.replace("_", " "),
            "source": "shop_api",
        }
        for i, t in enumerate(types)
    ]
    return dispute, evidence


def profit(action: str, outcome: str, amount: int) -> int:
    if action == "accept":
        return 0
    return (amount - EFFORT) if outcome == "won" else -(FEE + EFFORT)


def run(n_sellers: int) -> dict:
    rows = {"off": [], "on": [], "oracle": []}
    accept_right = {"off": [0, 0], "on": [0, 0]}
    for seed in range(1, n_sellers + 1):
        history = generate.build(seed=seed)
        store = InMemoryStore()
        seed_loader.load(store, history)
        for c in history["cases"]:
            if not c["holdout"] or c["outcome"] == "accepted":
                continue
            dispute, evidence = as_dispute(c)
            for mode in ("off", "on"):
                a = build_draft(dispute, evidence, store, memory_on=mode == "on")[
                    "advice"
                ]
                y = 1.0 if c["outcome"] == "won" else 0.0
                rows[mode].append(
                    {
                        "brier": (a["win_probability"] - y) ** 2,
                        "profit": profit(a["action"], c["outcome"], c["amount"]),
                    }
                )
                if a["action"] == "accept":
                    accept_right[mode][1] += 1
                    accept_right[mode][0] += c["outcome"] == "lost"
            p = c["true_win_probability"]
            oracle_action = (
                "fight" if p * c["amount"] - EFFORT - (1 - p) * FEE > 0 else "accept"
            )
            rows["oracle"].append(
                {"profit": profit(oracle_action, c["outcome"], c["amount"])}
            )
    return {"rows": rows, "accept_right": accept_right}


def report(res: dict, n_sellers: int) -> str:
    r = res["rows"]
    n = len(r["on"])
    f = lambda k, key: statistics.mean(x[key] for x in r[k])
    ar = res["accept_right"]
    pct = lambda a: f"{a[0]}/{a[1]}" if a[1] else "n/a"
    return f"""# Memory OFF vs ON: simulation on synthetic data

{n_sellers} simulated sellers, {n} fought held-out disputes. Outcomes are drawn from a hidden ground-truth win model,
so this shows the mechanism, not real-world performance. Reproduce: `python eval/run_eval.py --sellers {n_sellers}`.

| | Memory OFF | Memory ON | Oracle |
|---|---|---|---|
| Brier score of win probability (lower = better) | {f("off", "brier"):.3f} | {f("on", "brier"):.3f} | - |
| Mean profit per fought dispute (USD) | {f("off", "profit") / 100:.2f} | {f("on", "profit") / 100:.2f} | {f("oracle", "profit") / 100:.2f} |
| "Accept" advice that was right | {pct(ar["off"])} | {pct(ar["on"])} | - |
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sellers", type=int, default=40)
    args = ap.parse_args()
    print(report(run(args.sellers), args.sellers))
