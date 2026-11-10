# ruff: noqa: E501
"""MemoryStore backed by a self-hosted Hindsight server (REST, v1.2). One bank per seller: `seller-{id}`.

Mapping (verified against a running server):
- retain  -> POST /v1/default/banks/{bank}/memories   items[{content, timestamp(event date), tags, document_id, metadata}]
- recall  -> POST /v1/default/banks/{bank}/memories/recall   {query, tags, tags_match, budget}
- reflect -> POST /v1/default/banks/{bank}/reflect
- directives -> /directives (not returned by recall, so recall() prepends them)
- delete  -> DELETE /documents/{document_id}   (the memory id we hand out is the document_id)
Our memory `kind`, `verified` and `outcome` ride along as tags (`kind:case`, `verified:false`).
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime

import httpx

from .memory import KINDS, MemoryRef


def _bank(seller_id: str) -> str:
    return f"seller-{seller_id}"


class HindsightStore:
    def __init__(self, base_url: str = "http://localhost:8888", timeout: float = 180.0) -> None:
        self._http = httpx.Client(base_url=f"{base_url.rstrip('/')}/v1/default", timeout=timeout)

    def healthy(self) -> bool:
        try:
            return (
                httpx.get(
                    f"{self._http.base_url.scheme}://{self._http.base_url.host}:{self._http.base_url.port}/health",
                    timeout=3,
                ).status_code
                == 200
            )
        except httpx.HTTPError:
            return False

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
            verified = False
        doc_id = (
            memory_id or f"mem_{uuid.uuid4().hex[:10]}"
        )  # same document id replaces: idempotent
        item = {
            "content": content,
            "timestamp": datetime(event_date.year, event_date.month, event_date.day).isoformat()
            + "Z",
            "tags": [*tags, f"kind:{kind}", f"verified:{str(verified).lower()}"],
            "document_id": doc_id,
            "metadata": {k: str(v) for k, v in (meta or {}).items()},
        }
        # Free-tier LLM providers rate-limit fact extraction (Groq: 8k tokens/min, ~3k per retain), which
        # Hindsight reports as a 5xx. Back off and retry instead of losing the memory.
        for attempt in range(5):
            r = self._http.post(f"/banks/{_bank(seller_id)}/memories", json={"items": [item]})
            if r.status_code < 500 or attempt == 4:
                break
            time.sleep(15 * (attempt + 1))
        r.raise_for_status()
        return doc_id

    def recall(self, seller_id, query, *, tags=None, budget=8) -> list[MemoryRef]:
        bank = _bank(seller_id)
        out: list[MemoryRef] = []
        d = self._http.get(f"/banks/{bank}/directives")
        if d.status_code == 200:
            for x in d.json().get("items", d.json() if isinstance(d.json(), list) else []):
                if x.get("is_active", True):
                    out.append(
                        MemoryRef(
                            id=x["id"],
                            kind="directive",
                            text=x["content"],
                            confidence=1.0,
                            why="Seller directive applied to every draft",
                        )
                    )
        body = {"query": query, "budget": "low", "tags_match": "any"}
        if tags:
            body["tags"] = list(tags)
        r = self._http.post(f"/banks/{bank}/memories/recall", json=body)
        if r.status_code == 404:  # bank not created yet
            return out
        r.raise_for_status()
        seen: set[str] = set()
        for res in r.json().get("results", []):
            rtags = res.get("tags") or []
            kind = next((t.split(":", 1)[1] for t in rtags if t.startswith("kind:")), "case")
            ev = res.get("occurred_start") or res.get("mentioned_at")
            mem_id = res.get("document_id") or res["id"]
            if mem_id in seen:
                continue
            seen.add(mem_id)
            out.append(
                MemoryRef(
                    id=mem_id,
                    kind=kind if kind in KINDS else "case",
                    text=res["text"],
                    confidence=round(
                        min(1.0, float((res.get("scores") or {}).get("final", 0.5))), 2
                    ),
                    event_date=date.fromisoformat(ev[:10]) if ev else None,
                    verified="verified:false" not in rtags,
                    tags=[t for t in rtags if ":" in t],
                    why="Matches this dispute's reason, courier or customer",
                )
            )
        return out[:budget]

    def reflect(self, seller_id, question) -> str:
        r = self._http.post(
            f"/banks/{_bank(seller_id)}/reflect", json={"query": question, "budget": "low"}
        )
        r.raise_for_status()
        return r.json().get("text", "")

    def set_directive(self, seller_id, text) -> str:
        r = self._http.post(
            f"/banks/{_bank(seller_id)}/directives",
            json={"name": text[:60], "content": text, "priority": 10, "is_active": True},
        )
        r.raise_for_status()
        return r.json()["id"]

    def delete(self, seller_id, memory_id) -> None:
        bank = _bank(seller_id)
        if self._http.delete(f"/banks/{bank}/directives/{memory_id}").status_code == 200:
            return
        self._http.delete(f"/banks/{bank}/documents/{memory_id}")

    def delete_bank(self, seller_id) -> None:
        self._http.delete(f"/banks/{_bank(seller_id)}")
