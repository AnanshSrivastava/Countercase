"""Simulated bank outcome: demo only, guarded, and always marked as simulated."""

import pytest

from app.core.tables import DisputeRow
from app.settings import settings

from .p4_helpers import approve_body


def simulate(env, outcome="won", dispute="dp_t1"):
    return env.client.post(f"/core/disputes/{dispute}/simulate-outcome", json={"outcome": outcome})


def row(env, dispute="dp_t1") -> DisputeRow:
    env.session.expire_all()
    return env.session.get(DisputeRow, dispute)


def test_disabled_by_default_and_changes_nothing(env) -> None:
    env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env))
    resp = simulate(env)
    assert resp.status_code == 403 and resp.json()["error"] == "demo_tools_disabled"
    assert row(env).status == "submitted"


@pytest.fixture
def demo(env, monkeypatch):
    monkeypatch.setattr(settings, "demo_tools", True)
    return env


@pytest.mark.parametrize("outcome", ["won", "lost"])
def test_after_a_submission_it_sets_the_outcome_and_marks_it_simulated(demo, outcome) -> None:
    demo.client.post("/core/disputes/dp_t1/approve", json=approve_body(demo))
    resp = simulate(demo, outcome)
    assert resp.status_code == 200
    assert resp.json() == {"status": outcome, "simulated": "true"}
    assert row(demo).status == outcome
    assert row(demo).processor_status == f"simulated:{outcome}"


def test_also_works_after_an_export_so_the_demo_runs_without_a_stripe_key(demo) -> None:
    demo.fake.ok, demo.fake.why = False, "no Stripe test key is configured"
    demo.client.post("/core/disputes/dp_t1/approve", json=approve_body(demo))
    assert row(demo).status == "approved"
    assert simulate(demo, "won").status_code == 200


@pytest.mark.parametrize("status", ["needs_response", "drafted", "accepted"])
def test_refused_before_any_response_was_approved(demo, status) -> None:
    demo.session.get(DisputeRow, "dp_t1").status = status
    demo.session.commit()
    resp = simulate(demo)
    assert resp.status_code == 409 and resp.json()["error"] == "not_responded"
    assert row(demo).status == status


def test_cannot_overwrite_a_result(demo) -> None:
    demo.client.post("/core/disputes/dp_t1/approve", json=approve_body(demo))
    assert simulate(demo, "won").status_code == 200
    again = simulate(demo, "lost")
    assert again.status_code == 409
    assert row(demo).status == "won"


def test_unknown_dispute_and_bad_outcome(demo) -> None:
    assert simulate(demo, dispute="dp_nope").status_code == 404
    bad = demo.client.post("/core/disputes/dp_t1/simulate-outcome", json={"outcome": "maybe"})
    assert bad.status_code == 422 and bad.json()["error"] == "validation_error"


def test_processor_status_tells_the_ui_when_demo_tools_are_on(demo) -> None:
    assert demo.client.get("/core/processor-status").json()["demo_tools"] is True
