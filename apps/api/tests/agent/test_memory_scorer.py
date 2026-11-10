# ruff: noqa: E501
from datetime import date

import pytest

from app.agent.memory import InMemoryStore
from app.agent.scorer import advise, win_probability


def test_no_history_equals_prior_with_wide_interval():
    p, (lo, hi) = win_probability(0, 0, 0.45)
    assert p == pytest.approx(0.45) and hi - lo > 0.4


def test_history_moves_probability_and_narrows_interval():
    p0, i0 = win_probability(0, 0, 0.45)
    p1, i1 = win_probability(8, 2, 0.45)
    assert p1 > 0.6 > p0 and (i1[1] - i1[0]) < (i0[1] - i0[0])


def test_accept_when_claim_valid():
    a = advise(
        category="not_as_described",
        amount=4500,
        currency="usd",
        wins=5,
        losses=0,
        claim_looks_valid=True,
    )
    assert a.action == "accept"


def test_accept_below_directive_minimum_and_fight_otherwise():
    assert (
        advise(
            category="not_received", amount=2000, currency="usd", wins=2, losses=1, min_amount=5000
        ).action
        == "accept"
    )
    assert (
        advise(category="not_received", amount=12900, currency="usd", wins=2, losses=1).action
        == "fight"
    )


def test_recall_prefers_matching_tags_and_isolates_sellers():
    s = InMemoryStore()
    s.retain(
        "a",
        "Won not received with delivery photo",
        kind="case",
        tags=["reason:not_received", "courier:x"],
        event_date=date(2026, 8, 1),
    )
    s.retain(
        "a",
        "Lost unauthorized",
        kind="case",
        tags=["reason:unauthorized"],
        event_date=date(2026, 6, 1),
    )
    s.retain(
        "b",
        "Other seller's case",
        kind="case",
        tags=["reason:not_received"],
        event_date=date(2026, 8, 1),
    )
    got = s.recall("a", "not received dispute", tags=["reason:not_received"])
    assert got[0].text.startswith("Won not received") and all(
        "Other seller" not in m.text for m in got
    )


def test_directives_always_recalled_and_opinions_unverified():
    s = InMemoryStore()
    s.set_directive("a", "Always cite the 7-day return policy")
    oid = s.retain(
        "a",
        "customer seemed honest",
        kind="opinion",
        tags=[],
        event_date=date(2026, 9, 1),
        verified=True,
    )
    assert s.recall("a", "anything")[0].kind == "directive"
    assert next(m for m in s._banks["a"].values() if m.id == oid).verified is False
    s.delete("a", oid)
    assert oid not in s._banks["a"]
