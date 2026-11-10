# ruff: noqa: E501
"""LLM claim generator: the AI step of the dispute workflow.

The model only DRAFTS claims. Each claim must cite a verified evidence id and may only restate what
that evidence's summary says. The same validator that guards the template path then blocks any claim
whose evidence is missing or unverified, so a model mistake can be blocked but never submitted.

Any failure (no key, timeout, bad JSON, nothing usable) falls back to template_claims.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.agent.draft import template_claims
from app.agent.memory import MemoryRef
from app.settings import settings

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
SYSTEM = (
    "You draft the factual claims of a payment-dispute response for a small online seller. "
    "You are given the dispute and a list of VERIFIED evidence items, each with an id and a summary. "
    "Write 2 to 6 short claims. Every claim must cite exactly one evidence id from the list and may "
    "only state facts that evidence summary contains: no new facts, no guesses, no legal arguments, "
    "no mention of the customer's intent. Choose the evidence that best answers the dispute reason. "
    'Reply with ONLY a JSON array like [{"text": "...", "evidence_id": "ev_..."}].'
)


def _prompt(dispute: dict, evidence: list[dict]) -> str:
    lines = [f"- {e['id']} ({e['type']}): {e['summary']}" for e in evidence if e.get("verified")]
    return (
        f"Dispute reason: {dispute.get('category')} "
        f"({dispute.get('category_explanation') or dispute.get('reason_raw')}).\n"
        f"Amount (minor units): {dispute.get('amount')} {dispute.get('currency')}.\n"
        "Verified evidence:\n" + "\n".join(lines)
    )


def _parse(text: str, allowed: set[str]) -> list[dict]:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return []
    items = json.loads(text[start : end + 1])
    return [
        {"text": str(i["text"]).strip(), "evidence_id": i["evidence_id"]}
        for i in items
        if isinstance(i, dict)
        and i.get("evidence_id") in allowed
        and str(i.get("text", "")).strip()
    ]


def llm_claims(
    dispute: dict,
    evidence: list[dict],
    memory: list[MemoryRef],
    *,
    http: httpx.Client | None = None,
) -> list[dict]:
    allowed = {e["id"] for e in evidence if e.get("verified")}
    if not (settings.llm_api_key and settings.llm_model_draft and allowed):
        return template_claims(dispute, evidence, memory)
    try:
        client = http or httpx.Client(timeout=30.0)
        resp = client.post(
            API_URL,
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.llm_model_draft,
                "max_tokens": 800,
                "system": SYSTEM,
                "messages": [{"role": "user", "content": _prompt(dispute, evidence)}],
            },
        )
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json().get("content", []))
        claims = _parse(text, allowed)
        if claims:
            return claims
    except Exception:  # noqa: BLE001 - drafting must never take a dispute down
        log.warning("LLM claim generation failed; using templates", exc_info=True)
    return template_claims(dispute, evidence, memory)
