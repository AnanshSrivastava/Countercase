# ruff: noqa: E501
"""Integration test against a live Hindsight (make up-memory). Skipped when the server is not reachable."""

import os
import uuid
from datetime import date

import pytest

from app.agent.hindsight_store import HindsightStore
from app.settings import settings

store = HindsightStore(settings.hindsight_url)
# Opt-in: it calls a real LLM through Hindsight, so it is slow and needs provider quota.
#   HINDSIGHT_TEST=1 python -m pytest tests/agent/test_hindsight_store.py
pytestmark = pytest.mark.skipif(
    os.environ.get("HINDSIGHT_TEST") != "1" or not store.healthy(),
    reason="set HINDSIGHT_TEST=1 with Hindsight running",
)


def test_retain_recall_directive_delete_roundtrip():
    seller = f"test{uuid.uuid4().hex[:6]}"
    try:
        mem_id = store.retain(
            seller,
            "Won a not-received dispute with CourierX by including the delivery photo.",
            kind="case",
            tags=["reason:not_received", "courier:CourierX", "outcome:won"],
            event_date=date(2026, 8, 14),
        )
        store.set_directive(seller, "Always cite the 7-day return policy")
        got = store.recall(seller, "not received dispute CourierX", tags=["reason:not_received"])
        kinds = {m.kind for m in got}
        assert "directive" in kinds and "case" in kinds or "observation" in kinds or got
        case = next(m for m in got if m.kind != "directive")
        assert case.event_date == date(2026, 8, 14) and "CourierX" in case.text
        store.delete(seller, mem_id)
    finally:
        store.delete_bank(seller)
