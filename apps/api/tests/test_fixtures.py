"""Every fixture must validate against the CONTRACTS.md models, so drift is caught in CI."""

import json

import pytest

from app.core.models import Dispute, EvidenceItem
from app.settings import settings

DISPUTE_FILES = sorted((settings.fixtures_dir / "disputes").glob("*.json"))


def test_fixtures_present() -> None:
    assert len(DISPUTE_FILES) >= 3


@pytest.mark.parametrize("path", DISPUTE_FILES, ids=lambda p: p.name)
def test_dispute_fixture_matches_contract(path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    dispute = Dispute.model_validate(data["dispute"])
    evidence = [EvidenceItem.model_validate(e) for e in data["evidence"]]

    ids = {e.id for e in evidence}
    assert set(dispute.evidence) == ids, "dispute.evidence must list exactly the evidence ids"
    assert all(e.dispute_id == dispute.id for e in evidence)
    assert dispute.deadline_at > dispute.created_at
