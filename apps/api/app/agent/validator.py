# ruff: noqa: E501
"""F5 guardrail: every claim must cite an existing, verified evidence item, or it is dropped.

The letter is rendered only from validated claims, so an unsourced claim can never reach the seller's packet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # each has a "reason"


def validate_claims(claims: list[dict], evidence: list[dict]) -> ValidationResult:
    by_id = {e["id"]: e for e in evidence}
    result = ValidationResult()
    for claim in claims:
        ev = by_id.get(claim.get("evidence_id"))
        if ev is None:
            result.rejected.append({**claim, "reason": "unknown evidence id"})
        elif not ev.get("verified"):
            result.rejected.append({**claim, "reason": "evidence is not verified (seller claim)"})
        else:
            result.valid.append(claim)
    return result


def render_letter(
    claims: list[dict], evidence: list[dict], greeting: str = "To the dispute review team,"
) -> str:
    """Render markdown from validated claims only, with numbered source footnotes."""
    ids: list[str] = []
    sentences = []
    for claim in claims:
        if claim["evidence_id"] not in ids:
            ids.append(claim["evidence_id"])
        sentences.append(f"{claim['text']} [{ids.index(claim['evidence_id']) + 1}]")
    sources = ", ".join(f"[{i + 1}] {ev_id}" for i, ev_id in enumerate(ids))
    return f"{greeting}\n\n{' '.join(sentences)}\n\nSources: {sources}."
