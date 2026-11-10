# ruff: noqa: E501
import json
import sys

from app.agent import seed_loader
from app.agent.draft import build_draft
from app.agent.memory import InMemoryStore

HISTORY = json.loads(seed_loader.HISTORY.read_text(encoding="utf-8"))
sys.path.insert(0, str(seed_loader.HISTORY.parent))


def test_generator_is_deterministic_and_marked_synthetic():
    import generate

    assert HISTORY["synthetic"] is True
    assert generate.build() == HISTORY  # history.json must be regenerated when generate.py changes


def test_load_skips_holdout_and_marks_opinions_unverified():
    store = InMemoryStore()
    stats = seed_loader.load(store, HISTORY)
    bank = store._banks["sel_demo"]
    held = {c["id"] for c in HISTORY["cases"] if c["holdout"]}
    assert stats["cases"] == len(HISTORY["cases"]) - len(held)
    assert not any(
        m.text.startswith(("Won", "Lost")) and any(h in str(m.tags) for h in held)
        for m in bank.values()
    )
    assert all(not m.verified for m in bank.values() if m.kind == "opinion")
    assert sum(m.kind == "directive" for m in bank.values()) == len(HISTORY["directives"])


def test_demo_dispute_recalls_history_and_repeat_customer():
    store = InMemoryStore()
    seller_cases = seed_loader.load(store, HISTORY)["cases"]
    fx = json.loads(
        (
            seed_loader.HISTORY.parents[2] / "fixtures" / "disputes" / "dp_001_not_received.json"
        ).read_text(encoding="utf-8")
    )
    on = build_draft(fx["dispute"], fx["evidence"], store, memory_on=True)
    assert seller_cases > 30 and on["advice"]["n_cases"] >= 5
    assert any(
        m["kind"] == "customer_history" for m in on["memory"]
    )  # c_9f2a71d0's earlier dispute
    assert any(m["kind"] == "directive" for m in on["memory"])


def test_memory_never_knows_the_future():
    # The demo disputes open on 2026-10-01; no seeded outcome may be dated on or after that.
    assert all(c["resolved"] < "2026-10-01" for c in HISTORY["cases"])
    assert all(c["resolved"] >= c["created"] for c in HISTORY["cases"])
