# ruff: noqa: E501
"""A real Stripe `charge.dispute.closed` teaches the agent; simulated and repeated ones do not double count."""

import pytest
from fastapi.testclient import TestClient

from app.agent.beliefs import load_cases
from app.agent.memory import InMemoryStore
from app.agent.router import get_store
from app.core import outcome_report
from app.core.router import get_charge_lookup
from app.core.stripe_ingest import ChargeInfo
from app.main import app
from app.settings import settings

from .helpers import SECRET, make_event, send


@pytest.fixture
def client(session, monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    app.dependency_overrides[get_charge_lookup] = lambda: lambda charge_id: ChargeInfo()
    store = InMemoryStore()
    app.dependency_overrides.clear()
    get_store.cache_clear()
    monkeypatch.setattr("app.agent.router.get_store", lambda: store)
    app.dependency_overrides[get_charge_lookup] = lambda: lambda charge_id: ChargeInfo()
    yield TestClient(app), store
    app.dependency_overrides.clear()
    get_store.cache_clear()


def test_closed_won_is_reported_once(client) -> None:
    http, store = client
    send(http, make_event("e1", order_id="ord_101"))
    send(http, make_event("e2", kind="charge.dispute.closed", status="won", order_id="ord_101"))
    cases = load_cases(store, "sel_demo")
    assert len(cases) == 1 and "outcome:won" in cases[0].tags
    assert outcome_report.report_closed("du_ev_1") == "reported"  # repeat: still exactly one case
    assert len(load_cases(store, "sel_demo")) == 1


def test_open_dispute_is_not_reported(client) -> None:
    http, store = client
    send(http, make_event("e1", order_id="ord_101"))
    assert outcome_report.report_closed("du_ev_1") == "skipped"
    assert load_cases(store, "sel_demo") == []
