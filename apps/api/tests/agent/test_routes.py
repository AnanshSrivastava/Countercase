# ruff: noqa: E501
# ruff: noqa: E501
from fastapi.testclient import TestClient

from app.agent.router import get_store
from app.main import app

client = TestClient(app)


def test_classify():
    r = client.post("/agent/classify", json={"processor": "stripe", "reason_raw": "fraudulent"})
    assert r.status_code == 200 and r.json()["category"] == "unauthorized"


def test_draft_memory_on_vs_off():
    on = client.post("/agent/disputes/dp_001/draft?memory=on").json()
    off = client.post("/agent/disputes/dp_001/draft?memory=off").json()
    assert off["memory"] == [] and on["memory"] and on["advice"]["n_cases"] == 2
    assert on["claims"] == off["claims"]


def test_unknown_dispute_404_and_memory_delete():
    assert client.post("/agent/disputes/nope/draft").status_code == 404
    mem = client.get("/agent/memory", params={"dispute_id": "dp_001"}).json()
    victim = next(m["id"] for m in mem if m["kind"] == "directive")
    client.delete(f"/agent/memory/{victim}")
    after = client.get("/agent/memory", params={"dispute_id": "dp_001"}).json()
    assert victim not in {m["id"] for m in after}
    get_store.cache_clear()  # restore seed for other tests


def test_checklist_route_is_rules_only():
    r = client.get("/agent/disputes/dp_001/checklist").json()
    assert r["checklist"] and {"item", "status", "required"} <= r["checklist"][0].keys()


def test_full_seed_setting_loads_the_whole_history(monkeypatch):
    from app.agent.beliefs import load_cases
    from app.settings import settings

    monkeypatch.setattr(settings, "memory_seed", "full")
    get_store.cache_clear()
    try:
        assert len(load_cases(get_store(), "sel_demo")) > 40
    finally:
        get_store.cache_clear()
