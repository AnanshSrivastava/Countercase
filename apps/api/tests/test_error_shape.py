"""Every error from /core and /agent uses the contract shape {"error", "detail"}."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_unknown_route_404() -> None:
    resp = client.get("/core/does-not-exist")
    assert resp.status_code == 404
    assert resp.json() == {"error": "not_found", "detail": "Not Found"}


def test_wrong_method_405() -> None:
    resp = client.delete("/health")
    assert resp.status_code == 405
    assert resp.json()["error"] == "method_not_allowed"


def test_validation_error_422() -> None:
    resp = client.get("/core/disputes", params={"status": "not-a-status"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_error"
    assert "status" in body["detail"]


def test_agent_http_exception_with_contract_detail_passes_through() -> None:
    resp = client.post("/agent/disputes/nope/draft")
    assert resp.status_code == 404
    assert resp.json() == {"error": "not_found", "detail": "dispute nope"}
