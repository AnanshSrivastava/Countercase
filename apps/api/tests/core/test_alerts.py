# ruff: noqa: E501
"""Deadline alerts: right threshold, once only, only for disputes still waiting on the seller."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import alerts
from app.core.tables import AlertRow, DisputeRow
from app.main import app

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def add(session, did="dp_a", *, hours_left, status="needs_response", base=NOW):
    from app.core.disputes import ensure_seller

    ensure_seller(session, "sel_demo")
    session.add(
        DisputeRow(
            id=did,
            seller_id="sel_demo",
            processor="stripe",
            processor_dispute_id=f"du_{did}",
            amount=12900,
            currency="usd",
            reason_raw="product_not_received",
            category="not_received",
            status=status,
            created_at=base - timedelta(days=2),
            deadline_at=base + timedelta(hours=hours_left),
            customer_hash="c_1",
        )
    )
    session.commit()


class Recorder:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, subject, body):
        if self.fail:
            raise RuntimeError("smtp down")
        self.sent.append(subject)
        return alerts.Sent("email", "me@example.com")


@pytest.mark.parametrize(("left", "expected"), [(100, None), (70, 72), (20, 24), (5, 6)])
def test_threshold_chosen_by_time_left(session, left, expected):
    add(session, hours_left=left)
    sent = alerts.run_alerts(session, now=NOW, notifier=Recorder())
    assert [a.threshold_hours for a in sent] == ([expected] if expected else [])


def test_each_threshold_sends_once_and_next_one_follows(session):
    add(session, hours_left=70)
    rec = Recorder()
    assert len(alerts.run_alerts(session, now=NOW, notifier=rec)) == 1
    assert (
        alerts.run_alerts(session, now=NOW + timedelta(hours=1), notifier=rec) == []
    )  # same window: nothing new
    later = alerts.run_alerts(session, now=NOW + timedelta(hours=47), notifier=rec)  # 23h left
    assert [a.threshold_hours for a in later] == [24]


def test_late_discovery_sends_only_the_tightest_and_supersedes_the_rest(session):
    add(session, hours_left=5)
    sent = alerts.run_alerts(session, now=NOW, notifier=Recorder())
    assert [a.threshold_hours for a in sent] == [6]
    rows = {r.threshold_hours: r.status for r in session.query(AlertRow)}
    assert rows == {6: "sent", 24: "superseded", 72: "superseded"}
    assert (
        alerts.run_alerts(session, now=NOW, notifier=Recorder()) == []
    )  # superseded ones never fire later


@pytest.mark.parametrize("status", ["approved", "submitted", "accepted", "won", "lost"])
def test_disputes_not_waiting_on_the_seller_are_never_alerted(session, status):
    add(session, hours_left=5, status=status)
    assert alerts.run_alerts(session, now=NOW, notifier=Recorder()) == []


def test_overdue_dispute_is_not_alerted(session):
    add(session, hours_left=-3)
    assert alerts.run_alerts(session, now=NOW, notifier=Recorder()) == []


def test_without_smtp_the_alert_is_labelled_simulated(session):
    add(session, hours_left=20)
    [a] = alerts.run_alerts(session, now=NOW)
    assert a.channel == "simulated" and a.status == "sent"


def test_a_failing_mail_server_is_recorded_not_raised(session):
    add(session, "dp_a", hours_left=20)
    add(session, "dp_b", hours_left=20)
    out = alerts.run_alerts(session, now=NOW, notifier=Recorder(fail=True))
    assert len(out) == 2 and all(a.status == "failed" and "smtp down" in a.error for a in out)


def test_api_run_and_list(session):
    add(session, hours_left=1, base=datetime.now(UTC))  # the API uses the real clock
    client = TestClient(app)
    resp = client.post("/core/alerts/run")
    sent = resp.json()
    assert len(sent) == 1 and sent[0]["channel"] == "simulated"
    assert client.post("/core/alerts/run").json() == []
    assert len(client.get("/core/alerts").json()) == 1
