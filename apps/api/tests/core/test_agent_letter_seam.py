"""An unedited agent draft must render byte-identically through core's letter pipeline."""

from fastapi.testclient import TestClient

from app.core.disputes import seed_fixtures
from app.main import app

client = TestClient(app)


def test_unedited_agent_draft_is_identical_and_fully_sourced(session) -> None:
    seed_fixtures(session)
    draft = client.post("/agent/disputes/dp_001/draft?memory=off").json()
    assert draft["claims"], "fixture dispute should produce a rebuttal"

    preview = client.post(
        "/core/disputes/dp_001/letter-preview",
        json={"claims": draft["claims"], "seller_statement": None},
    ).json()
    assert preview["letter_md"] == draft["letter_md"]
    assert preview["blocked"] == []


def test_accept_draft_has_no_letter_and_previews_empty(session) -> None:
    seed_fixtures(session)
    draft = client.post("/agent/disputes/dp_003/draft?memory=off").json()
    claims = draft["claims"] if draft["advice"]["action"] == "fight" else []
    preview = client.post(
        "/core/disputes/dp_003/letter-preview", json={"claims": claims, "seller_statement": None}
    ).json()
    if draft["advice"]["action"] == "accept":
        assert draft["letter_md"] == "" and preview["letter_md"] == ""
    else:
        assert preview["letter_md"] == draft["letter_md"]
