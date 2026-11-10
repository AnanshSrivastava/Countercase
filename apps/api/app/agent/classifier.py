# ruff: noqa: E501
"""F2 reason-code classifier and F3 evidence checklist (rules first; LLM fallback comes later)."""

from __future__ import annotations

from dataclasses import dataclass

from .rules import CHECKLISTS, PAYPAL_REASONS, STRIPE_REASONS

REASONS = {"stripe": STRIPE_REASONS, "paypal": PAYPAL_REASONS}


@dataclass(frozen=True)
class Classification:
    category: str
    explanation: str
    needs_review: bool = False  # True when the code was unknown (candidate for LLM fallback)


def classify(processor: str, reason_raw: str) -> Classification:
    table = REASONS.get(processor, {})
    if reason_raw in table:
        category, explanation = table[reason_raw]
        return Classification(category, explanation)
    return Classification(
        "other", "We could not map this reason code automatically.", needs_review=True
    )


def build_checklist(category: str, evidence: list[dict]) -> list[dict]:
    """Return checklist rows {item, status, evidence_id, required}. Only verified evidence counts as available."""
    spec = CHECKLISTS.get(category, CHECKLISTS["other"])
    rows = []
    for level in ("required", "optional"):
        for ev_type, label in spec[level]:
            match = next((e for e in evidence if e["type"] == ev_type and e.get("verified")), None)
            rows.append(
                {
                    "item": label,
                    "status": "available" if match else "missing",
                    "evidence_id": match["id"] if match else None,
                    "required": level == "required",
                }
            )
    return rows
