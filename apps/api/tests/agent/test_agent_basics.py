# ruff: noqa: E501
import json
from pathlib import Path

import pytest

from app.agent.classifier import build_checklist, classify
from app.agent.validator import render_letter, validate_claims

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"


def load(name):
    name = {
        "dp_001": "dp_001_not_received",
        "dp_002": "dp_002_unauthorized",
        "dp_003": "dp_003_not_as_described",
    }[name]
    return json.loads((FIXTURES / "disputes" / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["dp_001", "dp_002", "dp_003"])
def test_fixture_dispute_classified_as_stored(name):
    d = load(name)["dispute"]
    assert classify(d["processor"], d["reason_raw"]).category == d["category"]


def test_unknown_reason_needs_review():
    c = classify("stripe", "some_new_code")
    assert c.category == "other" and c.needs_review


def test_checklist_uses_only_verified_evidence():
    data = load("dp_001")
    rows = {r["item"]: r for r in build_checklist("not_received", data["evidence"])}
    assert rows["Order receipt"]["status"] == "available"
    assert rows["Delivery proof (tracking, photo, signature)"]["evidence_id"] == "ev_1"
    assert (
        rows["Customer communication"]["status"] == "missing"
    )  # only an unverified seller note exists


def test_unsourced_and_unverified_claims_are_rejected():
    evidence = load("dp_001")["evidence"]
    claims = [
        {"text": "Delivered 28 Sep.", "evidence_id": "ev_1"},
        {"text": "Customer is honest.", "evidence_id": "ev_4"},  # seller_note, verified=false
        {"text": "Signed by the customer's spouse.", "evidence_id": "ev_999"},  # invented
        {"text": "No evidence id at all."},
    ]
    result = validate_claims(claims, evidence)
    assert [c["evidence_id"] for c in result.valid] == ["ev_1"]
    assert len(result.rejected) == 3


def test_letter_contains_only_valid_claims():
    evidence = load("dp_001")["evidence"]
    result = validate_claims(
        [
            {"text": "Delivered 28 Sep.", "evidence_id": "ev_1"},
            {"text": "Made up.", "evidence_id": "ev_9"},
        ],
        evidence,
    )
    letter = render_letter(result.valid, evidence)
    assert "Delivered 28 Sep. [1]" in letter and "Made up" not in letter
