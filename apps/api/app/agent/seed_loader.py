# ruff: noqa: E501
"""Load data/seed/history.json (SYNTHETIC) into a MemoryStore as the demo seller's past.

    python -m app.agent.seed_loader --backend inmemory
    python -m app.agent.seed_loader --backend hindsight --url http://localhost:8888 --pace 25

Memory text is built from structured fields by template (IMPROVEMENTS #8): no free LLM prose, no raw PII.
Held-out cases are never loaded, so evaluation can't leak their outcomes into recall.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from .hindsight_store import HindsightStore
from .memory import InMemoryStore, MemoryStore

HISTORY = Path(__file__).resolve().parents[4] / "data" / "seed" / "history.json"


def case_text(c: dict) -> str:
    money = f"{c['amount'] / 100:.2f} {c['currency'].upper()}"
    ev = ", ".join(e.replace("_", " ") for e in c["evidence"])
    verb = {"won": "Won", "lost": "Lost", "accepted": "Accepted without fighting"}[c["outcome"]]
    return (
        f"{verb} a '{c['category'].replace('_', ' ')}' dispute for {c['sku']} ({money}) shipped by {c['courier']}. "
        f"Evidence submitted: {ev}."
    )


def case_tags(c: dict) -> list[str]:
    return [
        f"reason:{c['category']}",
        f"courier:{c['courier']}",
        f"product:{c['sku']}",
        f"customer:{c['customer']}",
        f"outcome:{c['outcome']}",
        "processor:stripe",
        *[f"evidence:{e}" for e in c["evidence"]],
    ]


def load(store: MemoryStore, history: dict, *, pace: float = 0.0, limit: int | None = None) -> dict:
    seller = history["seller_id"]
    n_cases = n_other = 0
    cases = [c for c in history["cases"] if not c["holdout"]][: limit or None]
    for c in cases:
        store.retain(
            seller,
            case_text(c),
            kind="case",
            tags=case_tags(c),
            event_date=date.fromisoformat(c["resolved"]),
            meta={"case_id": c["id"]},
        )
        n_cases += 1
        if c.get("note"):  # a seller-confirmed fact about this customer, tied to the case
            store.retain(
                seller,
                f"Customer {c['customer']}: {c['note']}",
                kind="customer_history",
                tags=[f"customer:{c['customer']}", f"reason:{c['category']}"],
                event_date=date.fromisoformat(c["resolved"]),
            )
            n_other += 1
        time.sleep(pace)
    for text in history["directives"]:
        store.set_directive(seller, text)
        n_other += 1
    for text in history["opinions"]:
        store.retain(
            seller,
            text,
            kind="opinion",
            tags=["opinion"],
            event_date=date(2026, 9, 15),
            verified=False,
        )
        n_other += 1
        time.sleep(pace)
    return {
        "cases": n_cases,
        "other": n_other,
        "held_out": sum(c["holdout"] for c in history["cases"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["inmemory", "hindsight"], default="inmemory")
    ap.add_argument("--url", default="http://localhost:8888")
    ap.add_argument(
        "--pace", type=float, default=0.0, help="seconds between retains (Groq free tier: ~25)"
    )
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--file", type=Path, default=HISTORY)
    ap.add_argument("--reset", action="store_true", help="hindsight: delete the seller bank first")
    args = ap.parse_args()
    history = json.loads(args.file.read_text(encoding="utf-8"))
    store: MemoryStore = (
        HindsightStore(args.url) if args.backend == "hindsight" else InMemoryStore()
    )
    if args.backend == "hindsight" and args.reset:
        store.delete_bank(history["seller_id"])  # type: ignore[attr-defined]
    print(load(store, history, pace=args.pace, limit=args.limit))


if __name__ == "__main__":
    main()
