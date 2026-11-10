"""The JSON examples in docs/CONTRACTS.md must validate against the core models."""

import json
import re

import pytest

from app.core.models import Dispute, EvidenceItem, Seller, Submission
from app.settings import settings

CONTRACTS = settings.fixtures_dir.parent / "docs" / "CONTRACTS.md"
MODELS = {
    "Dispute": Dispute,
    "Seller": Seller,
    "Submission": Submission,
    "EvidenceItem": EvidenceItem,
}


def _examples() -> dict[str, dict]:
    text = CONTRACTS.read_text(encoding="utf-8")
    found = {}
    for heading, block in re.findall(r"### (\w+)[^\n]*\n```json\n(.*?)```", text, re.S):
        if heading in MODELS:
            found[heading] = json.loads(block)
    return found


def test_all_core_entities_documented() -> None:
    assert set(_examples()) == set(MODELS)


@pytest.mark.parametrize("name", sorted(MODELS))
def test_contract_example_validates(name: str) -> None:
    MODELS[name].model_validate(_examples()[name])
