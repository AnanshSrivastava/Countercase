"""The response letter: validation, rendering and the review hash (F5).

Rule 5 is enforced here, on the server, independent of the agent and of whatever the browser sent:
every claim must cite an evidence item that exists on THIS dispute and is verified (pulled from a
system, never supplied by the seller). Wording stays editable; the source link does not.

The letter body is rendered by the agent's own `render_letter`, so an unedited draft is
byte-identical to the agent's `letter_md`. The seller's free text goes only into a clearly labelled
"statement" section that is never presented as evidence.
"""

import hashlib
import json

from app.agent.validator import render_letter
from app.core.models import BlockedClaim, Claim
from app.core.tables import EvidenceRow

SELLER_STATEMENT_HEADING = "Statement from the seller (not independently verified evidence):"

# Stripe test-mode magic values that would force a simulated outcome. Never allowed in a response.
RESERVED_TEXT = ("winning_evidence", "losing_evidence", "escalate_inquiry_evidence")


def check_claims(claims: list[Claim], evidence: dict[str, EvidenceRow]) -> list[BlockedClaim]:
    blocked = []
    for i, claim in enumerate(claims):
        ev = evidence.get(claim.evidence_id)
        if ev is None:
            reason = "this evidence does not exist on this dispute"
        elif not ev.verified:
            reason = "only data from your shop, courier or Stripe can back a claim"
        else:
            continue
        blocked.append(BlockedClaim(index=i, evidence_id=claim.evidence_id, reason=reason))
    return blocked


def reserved_text_in(*texts: str | None) -> str | None:
    blob = " ".join(t for t in texts if t).lower()
    return next((word for word in RESERVED_TEXT if word in blob), None)


def render_final_letter(claims: list[Claim], seller_statement: str | None) -> str:
    """Empty string when there are no claims: a response with no sourced claim is not a response."""
    if not claims:
        return ""
    letter = render_letter([c.model_dump() for c in claims], [])
    statement = (seller_statement or "").strip()
    if statement:
        letter = f"{letter}\n\n{SELLER_STATEMENT_HEADING}\n{statement}"
    return letter


def letter_hash(
    letter_md: str,
    claims: list[Claim],
    attachments: list[str],
    records: dict[str, EvidenceRow],
) -> str:
    """Binds an approval to what the seller reviewed: the letter, the cited source records word
    for word (the PDF reproduces them), and the attachments. If a source record is re-collected
    and its text changes, an earlier preview no longer matches."""
    ordered = list(dict.fromkeys(c.evidence_id for c in claims))
    sources = [
        [i, records[i].summary, records[i].captured_at.isoformat()] if i in records else [i]
        for i in ordered
    ]
    payload = {"letter": letter_md, "sources": sources, "attachments": sorted(attachments)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
