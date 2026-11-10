# ruff: noqa: E501
"""MemoryStore interface (docs/CONTRACTS.md section 3) plus an in-memory implementation.

HindsightStore will implement the same Protocol; everything else in `agent/` depends only on this interface.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

KINDS = ("case", "belief", "directive", "mental_model", "pattern", "customer_history", "opinion")


@dataclass
class MemoryRef:
    id: str
    kind: str
    text: str
    confidence: float = 1.0
    n_supporting: int = 1
    event_date: date | None = None
    used: bool = True
    why: str = ""
    editable: bool = True
    verified: bool = True
    tags: list[str] = field(default_factory=list)


class MemoryStore(Protocol):
    def retain(
        self,
        seller_id: str,
        content: str,
        *,
        kind: str,
        tags: list[str],
        event_date: date,
        verified: bool = True,
        meta: dict | None = None,
        memory_id: str | None = None,
    ) -> str: ...

    def recall(
        self, seller_id: str, query: str, *, tags: list[str] | None = None, budget: int = 8
    ) -> list[MemoryRef]: ...

    def reflect(self, seller_id: str, question: str) -> str: ...

    def set_directive(self, seller_id: str, text: str) -> str: ...

    def delete(self, seller_id: str, memory_id: str) -> None: ...


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_:]+", text.lower()))


class InMemoryStore:
    """Dict-backed store for tests and offline demos. Per-seller isolation is enforced by construction."""

    def __init__(self) -> None:
        self._banks: dict[str, dict[str, MemoryRef]] = {}

    def retain(
        self,
        seller_id,
        content,
        *,
        kind,
        tags,
        event_date,
        verified=True,
        meta=None,
        memory_id=None,
    ) -> str:
        if kind not in KINDS:
            raise ValueError(f"unknown memory kind: {kind}")
        if kind == "opinion":
            verified = False  # seller claims are never facts
        mem_id = (
            memory_id or f"mem_{uuid.uuid4().hex[:8]}"
        )  # a given id replaces: retain is idempotent
        self._banks.setdefault(seller_id, {})[mem_id] = MemoryRef(
            id=mem_id,
            kind=kind,
            text=content,
            event_date=event_date,
            verified=verified,
            tags=[*tags, f"kind:{kind}"],
            confidence=(meta or {}).get("confidence", 1.0),
            n_supporting=(meta or {}).get("n_supporting", 1),
        )
        return mem_id

    def recall(self, seller_id, query, *, tags=None, budget=8) -> list[MemoryRef]:
        """Rank by tag overlap (strong signal) then keyword overlap then recency. Directives always included."""
        bank = self._banks.get(seller_id, {})
        q = _tokens(query)
        wanted = set(tags or [])
        scored = []
        for m in bank.values():
            tag_hits = len(wanted & set(m.tags))
            word_hits = len(q & _tokens(m.text))
            if m.kind == "directive":
                score = 100.0
            else:
                score = tag_hits * 10 + word_hits
            if score > 0:
                scored.append((score, m.event_date or date.min, m))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        return [m for _, _, m in scored[:budget]]

    def reflect(self, seller_id, question):
        raise NotImplementedError("reflect needs an LLM; implemented by HindsightStore")

    def set_directive(self, seller_id, text) -> str:
        for m in self._banks.get(seller_id, {}).values():  # saving the same rule twice is a no-op
            if m.kind == "directive" and m.text.strip().lower() == text.strip().lower():
                return m.id
        return self.retain(
            seller_id, text, kind="directive", tags=["directive"], event_date=date.today()
        )

    def delete(self, seller_id, memory_id) -> None:
        self._banks.get(seller_id, {}).pop(memory_id, None)
