# ruff: noqa: E501
import json

from sqlalchemy import func, select

from app.agent import seed_core
from app.core.disputes import get_dispute
from app.core.tables import DisputeRow


def test_history_seeds_idempotently_and_reads_back(session):
    history = json.loads(seed_core.HISTORY.read_text(encoding="utf-8"))
    assert seed_core.seed_history(session, history) == len(history["cases"])
    seed_core.seed_history(session, history)  # twice: no duplicates, no constraint errors
    assert session.scalar(select(func.count()).select_from(DisputeRow)) == len(history["cases"])
    first = history["cases"][0]
    detail = get_dispute(session, first["id"])
    assert (
        detail.dispute.status == first["outcome"] and detail.dispute.category == first["category"]
    )
    assert all(e.verified for e in detail.evidence) and detail.evidence
