import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.disputes import seed_fixtures
from app.core.models import DisputeDetail
from app.core.tables import EvidenceRow
from app.main import app
from app.settings import settings

client = TestClient(app)


def _fixture(name: str) -> DisputeDetail:
    path = settings.fixtures_dir / "disputes" / name
    return DisputeDetail.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_seed_is_idempotent(session) -> None:
    assert seed_fixtures(session) == 3
    assert seed_fixtures(session) == 3
    assert len(client.get("/core/disputes").json()) == 3


def test_detail_matches_fixture_exactly(session) -> None:
    seed_fixtures(session)
    resp = client.get("/core/disputes/dp_001")
    assert resp.status_code == 200
    got = DisputeDetail.model_validate(resp.json())
    want = _fixture("dp_001_not_received.json")
    assert got.dispute.model_dump(exclude={"evidence"}) == want.dispute.model_dump(
        exclude={"evidence"}
    )
    assert set(got.dispute.evidence) == set(want.dispute.evidence)
    assert {e.id: e for e in got.evidence} == {e.id: e for e in want.evidence}


def test_list_sorted_by_deadline_and_filterable(session) -> None:
    seed_fixtures(session)
    rows = client.get("/core/disputes").json()
    deadlines = [datetime.fromisoformat(r["deadline_at"]) for r in rows]
    assert deadlines == sorted(deadlines)
    assert client.get("/core/disputes", params={"status": "won"}).json() == []


def test_missing_dispute_uses_contract_error_shape(session) -> None:
    resp = client.get("/core/disputes/dp_nope")
    assert resp.status_code == 404
    assert resp.json() == {"error": "not_found", "detail": "dispute dp_nope not found"}


def test_db_rejects_verified_seller_claim(session) -> None:
    seed_fixtures(session)
    session.add(
        EvidenceRow(
            id="ev_bad",
            dispute_id="dp_001",
            type="seller_note",
            source="seller_claim",
            verified=True,
            summary="must never be stored as verified",
            captured_at=datetime(2026, 10, 1, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
