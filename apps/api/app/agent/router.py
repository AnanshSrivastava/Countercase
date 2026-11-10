# ruff: noqa: E501
"""Agent router (owner: Shivansh). Mounted at /agent.

Dispute data comes from a DisputeSource. Until Lakshya's /core/disputes endpoints are live it reads
fixtures/disputes/*.json; swap `get_source` for an HTTP client to /core when ready (no route changes needed).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.settings import settings

from .beliefs import (
    CHANGE_LOG,
    DISMISSED,
    build_playbook,
    compute_beliefs,
    load_cases,
    propose_directives,
    record_outcome,
)
from .classifier import build_checklist, classify
from .draft import build_draft
from .hindsight_store import HindsightStore
from .llm_claims import llm_claims
from .memory import InMemoryStore, MemoryStore

router = APIRouter()


class FixtureSource:
    def get(self, dispute_id: str) -> dict | None:
        for path in sorted((settings.fixtures_dir / "disputes").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["dispute"]["id"] == dispute_id:
                return data
        return None


class CoreSource:
    """Reads a dispute straight from core's DB layer (same process), shaped like the fixtures."""

    def get(self, dispute_id: str) -> dict | None:
        from app.core.db import session_factory
        from app.core.disputes import get_dispute

        with session_factory()() as session:
            detail = get_dispute(session, dispute_id)
        return detail.model_dump(mode="json") if detail else None


class AutoSource:
    """core first; if the DB is unreachable (local dev without `make up`) fall back to fixtures."""

    def __init__(self) -> None:
        self._core, self._fixtures = CoreSource(), FixtureSource()

    def get(self, dispute_id: str) -> dict | None:
        try:
            return self._core.get(dispute_id)
        except SQLAlchemyError:
            return self._fixtures.get(dispute_id)


@lru_cache
def get_source() -> FixtureSource | CoreSource | AutoSource:
    return {"core": CoreSource, "fixtures": FixtureSource}.get(
        settings.dispute_source, AutoSource
    )()


def seed_demo(store: MemoryStore, seller_id: str = "sel_demo") -> None:
    """Small demo history so memory ON differs from OFF. Replaced by data/seed/ generator later (synthetic)."""
    for d, outcome in (
        (date(2026, 7, 3), "won"),
        (date(2026, 8, 14), "won"),
        (date(2026, 9, 2), "lost"),
    ):
        store.retain(
            seller_id,
            f"{outcome.title()} 'not received' dispute (CourierX)",
            kind="case",
            event_date=d,
            tags=[
                "reason:not_received",
                "courier:CourierX",
                f"outcome:{outcome}",
                *(["evidence:delivery_photo"] if outcome == "won" else []),
            ],
        )
    store.set_directive(seller_id, "Always cite the 7-day return policy")


@lru_cache
def get_store() -> MemoryStore:
    if (
        settings.memory_backend == "hindsight"
    ):  # history comes from the seed script (rate-limited LLM)
        return HindsightStore(settings.hindsight_url)
    store = InMemoryStore()
    if (
        settings.memory_seed == "full"
    ):  # Hindsight-free demo: the whole synthetic history, no LLM quota
        from .seed_loader import HISTORY
        from .seed_loader import load as load_history

        load_history(store, json.loads(HISTORY.read_text(encoding="utf-8")))
    else:
        seed_demo(store)
    return store


class ClassifyRequest(BaseModel):
    processor: str
    reason_raw: str


@router.post("/classify")
def classify_route(req: ClassifyRequest) -> dict:
    c = classify(req.processor, req.reason_raw)
    return {"category": c.category, "explanation": c.explanation, "needs_review": c.needs_review}


@router.post("/disputes/{dispute_id}/draft")
def draft_route(dispute_id: str, memory: Literal["on", "off"] = Query("on")) -> dict:
    data = get_source().get(dispute_id)
    if data is None:
        raise HTTPException(404, detail={"error": "not_found", "detail": f"dispute {dispute_id}"})
    return build_draft(
        data["dispute"],
        data["evidence"],
        get_store(),
        memory_on=memory == "on",
        generate_claims=llm_claims,
    )


@router.get("/memory")
def memory_route(dispute_id: str) -> list[dict]:
    """Inspector data: what memory 'on' would recall for this dispute."""
    return build_draft_memory(dispute_id)


def build_draft_memory(dispute_id: str) -> list[dict]:
    data = get_source().get(dispute_id)
    if data is None:
        raise HTTPException(404, detail={"error": "not_found", "detail": f"dispute {dispute_id}"})
    return build_draft(data["dispute"], data["evidence"], get_store(), memory_on=True)["memory"]


@router.delete("/memory/{memory_id}")
def delete_memory(memory_id: str, seller_id: str = "sel_demo") -> dict:
    get_store().delete(seller_id, memory_id)
    return {"deleted": memory_id}


# ---- M2/M3/M5/M7: outcomes, beliefs, edit learning, playbook ----


class OutcomeRequest(BaseModel):
    outcome: Literal["won", "lost"]
    closed_at: date | None = None


class EditRequest(BaseModel):
    before: str
    after: str
    decision: Literal["fight", "accept"] | None = None


class DirectiveRequest(BaseModel):
    text: str
    seller_id: str = "sel_demo"


def _dispute_or_404(dispute_id: str) -> dict:
    data = get_source().get(dispute_id)
    if data is None:
        raise HTTPException(404, detail={"error": "not_found", "detail": f"dispute {dispute_id}"})
    return data


@router.post("/disputes/{dispute_id}/outcome")
def outcome_route(dispute_id: str, req: OutcomeRequest) -> dict:
    """Retain the confirmed outcome and report how beliefs moved ('confidence 60% -> 85%')."""
    data = _dispute_or_404(dispute_id)
    types = {e["type"] for e in data["evidence"] if e.get("verified")}
    changes = record_outcome(
        get_store(), data["dispute"], types, req.outcome, req.closed_at or date.today()
    )
    return {"dispute_id": dispute_id, "outcome": req.outcome, "belief_changes": changes}


@router.get("/beliefs")
def beliefs_route(seller_id: str = "sel_demo") -> list[dict]:
    cases = load_cases(get_store(), seller_id)
    return [asdict(b) for b in compute_beliefs(cases, DISMISSED.get(seller_id, set()))]


@router.get("/beliefs/changes")
def belief_changes_route(since: str | None = None) -> list[dict]:
    return [c for c in CHANGE_LOG if since is None or c["at"] >= since]


@router.delete("/beliefs/{key:path}")
def dismiss_belief(key: str, seller_id: str = "sel_demo") -> dict:
    DISMISSED.setdefault(seller_id, set()).add(key)
    return {"dismissed": key}


@router.post("/disputes/{dispute_id}/edit")
def edit_route(dispute_id: str, req: EditRequest) -> dict:
    """Fast signal: propose (never auto-save) directives learned from the seller's edit or decision."""
    data = _dispute_or_404(dispute_id)
    return {
        "proposals": propose_directives(
            req.before, req.after, req.decision, data["dispute"]["amount"]
        )
    }


@router.post("/directives")
def create_directive(req: DirectiveRequest) -> dict:
    """Seller confirmed a proposed rule."""
    return {"id": get_store().set_directive(req.seller_id, req.text), "text": req.text}


@router.get("/playbook")
def playbook_route(seller_id: str = "sel_demo") -> dict:
    store = get_store()
    cases = load_cases(store, seller_id)
    directives = [m for m in store.recall(seller_id, "seller rules") if m.kind == "directive"]
    return build_playbook(cases, directives, DISMISSED.get(seller_id, set()))


@router.get("/disputes/{dispute_id}/checklist")
def checklist_route(dispute_id: str) -> dict:
    """Cheap, rules-only checklist (no memory, no model): safe to call on every page view."""
    data = _dispute_or_404(dispute_id)
    return {
        "dispute_id": dispute_id,
        "checklist": build_checklist(data["dispute"]["category"], data["evidence"]),
    }
