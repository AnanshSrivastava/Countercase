# ruff: noqa: E501
"""M2/M4/M5/M7: beliefs with confidence, outcome recording, edit learning and the Seller Playbook.

Beliefs are DERIVED from the seller's retained cases by counting, never written by an LLM, so they can't
drift or hallucinate. Each has a confidence, the number of cases behind it, and an honest label:
  weak (n < 6) | moderate | strong (n >= 8 and confidence >= 0.8)
Only confirmed outcomes move beliefs. Edits and decisions only *propose* directives (seller confirms).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

from .memory import MemoryRef, MemoryStore
from .rules import EVIDENCE_LABEL, KEY_EVIDENCE, strong_evidence

MIN_SIDE = 2  # cases needed on each side of a comparison before a belief forms
RECENT_DAYS = 60


@dataclass(frozen=True)
class Belief:
    key: str
    text: str
    confidence: float
    n: int
    label: str  # weak | moderate | strong
    kind: str  # evidence | courier

    def as_memory_ref(self) -> MemoryRef:
        return MemoryRef(
            id=f"belief:{self.key}",
            kind="belief",
            text=self.text,
            confidence=self.confidence,
            n_supporting=self.n,
            why=f"Derived from {self.n} of your past cases ({self.label})",
            tags=[self.key],
        )


def _label(n: int, conf: float) -> str:
    return "weak" if n < 6 else ("strong" if n >= 8 and conf >= 0.8 else "moderate")


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _prob_better(w1: int, l1: int, w2: int, l2: int) -> float:
    """P(rate1 > rate2) under Beta(1+w, 1+l) posteriors, normal approximation."""

    def stats(w: int, lo: int) -> tuple[float, float]:
        a, b = 1 + w, 1 + lo
        return a / (a + b), a * b / ((a + b) ** 2 * (a + b + 1))

    m1, v1 = stats(w1, l1)
    m2, v2 = stats(w2, l2)
    return _phi((m1 - m2) / math.sqrt(v1 + v2))


def _outcome(m: MemoryRef) -> str | None:
    return "won" if "outcome:won" in m.tags else ("lost" if "outcome:lost" in m.tags else None)


def _cases(memory: list[MemoryRef]) -> list[MemoryRef]:
    return [m for m in memory if m.kind == "case" and _outcome(m)]


def compute_beliefs(
    memory: list[MemoryRef], dismissed: set[str] | frozenset[str] = frozenset()
) -> list[Belief]:
    return [b for b in _compute(memory) if b.key not in dismissed]


def _compute(memory: list[MemoryRef]) -> list[Belief]:
    cases = _cases(memory)
    out: list[Belief] = []
    for category, keys in KEY_EVIDENCE.items():
        in_cat = [m for m in cases if f"reason:{category}" in m.tags]

        def has_key(m: MemoryRef, category: str = category) -> bool:
            return bool(
                strong_evidence(
                    {t.split(":", 1)[1] for t in m.tags if t.startswith("evidence:")}, category
                )
            )

        with_, without = [m for m in in_cat if has_key(m)], [m for m in in_cat if not has_key(m)]
        if len(with_) < MIN_SIDE or len(without) < MIN_SIDE:
            continue
        w1, l1 = sum(_outcome(m) == "won" for m in with_), sum(_outcome(m) == "lost" for m in with_)
        w2, l2 = (
            sum(_outcome(m) == "won" for m in without),
            sum(_outcome(m) == "lost" for m in without),
        )
        r1, r2 = w1 / len(with_), w2 / len(without)
        if r1 <= r2:
            continue
        conf = round(_prob_better(w1, l1, w2, l2), 2)
        label = EVIDENCE_LABEL[next(iter(keys))]
        n = len(with_) + len(without)
        out.append(
            Belief(
                key=f"evidence:{category}",
                text=f"{label} wins '{category.replace('_', ' ')}' disputes ({r1:.0%} won with it vs {r2:.0%} without)",
                confidence=conf,
                n=n,
                label=_label(n, conf),
                kind="evidence",
            )
        )
    dates = [m.event_date for m in cases if m.event_date]
    if dates:
        since = max(dates) - timedelta(days=RECENT_DAYS)
        lost = [
            m for m in cases if _outcome(m) == "lost" and m.event_date and m.event_date >= since
        ]
        couriers = Counter(
            t.split(":", 1)[1] for m in lost for t in m.tags if t.startswith("courier:")
        )
        if len(lost) >= 4 and couriers:
            name, k = couriers.most_common(1)[0]
            share = k / len(lost)
            overall = sum(f"courier:{name}" in m.tags for m in cases) / len(cases)
            if share >= 0.5 and share > overall + 0.1:
                conf = round((k + 1) / (len(lost) + 2), 2)
                out.append(
                    Belief(
                        key=f"courier:{name}",
                        text=f"{name} is involved in {share:.0%} of your lost disputes since {since.isoformat()} ({k} of {len(lost)})",
                        confidence=conf,
                        n=len(lost),
                        label=_label(len(lost), conf),
                        kind="courier",
                    )
                )
    return out


def load_cases(store: MemoryStore, seller_id: str) -> list[MemoryRef]:
    return [
        m
        for m in store.recall(seller_id, "dispute outcomes", tags=["kind:case"], budget=500)
        if m.kind == "case"
    ]


def belief_changes(before: list[Belief], after: list[Belief]) -> list[dict]:
    b = {x.key: x for x in before}
    changes = []
    for a in after:
        prev = b.get(a.key)
        if prev is None:
            changes.append(
                {
                    "key": a.key,
                    "text": a.text,
                    "before": None,
                    "after": a.confidence,
                    "label": a.label,
                    "status": "formed",
                }
            )
        elif a.confidence != prev.confidence:
            changes.append(
                {
                    "key": a.key,
                    "text": a.text,
                    "before": prev.confidence,
                    "after": a.confidence,
                    "label": a.label,
                    "status": "updated",
                }
            )
    for key, prev in b.items():
        if key not in {a.key for a in after}:
            changes.append(
                {
                    "key": key,
                    "text": prev.text,
                    "before": prev.confidence,
                    "after": None,
                    "label": "gone",
                    "status": "dropped",
                }
            )
    return changes


DISMISSED: dict[str, set[str]] = {}  # seller_id -> belief keys the seller rejected (M6)
CHANGE_LOG: list[dict] = []  # in-process log behind GET /agent/beliefs/changes (single-seller demo)


def record_outcome(
    store: MemoryStore, dispute: dict, evidence_types: set[str], outcome: str, closed: date
) -> list[dict]:
    """Retain the confirmed outcome as a case, then report how beliefs moved."""
    seller = dispute["seller_id"]
    dismissed = DISMISSED.get(seller, set())
    before = compute_beliefs(load_cases(store, seller), dismissed)
    cat = dispute["category"]
    tags = [
        f"reason:{cat}",
        f"courier:{dispute.get('courier')}",
        f"product:{dispute.get('product_sku')}",
        f"customer:{dispute.get('customer_hash')}",
        f"outcome:{outcome}",
        "processor:stripe",
        *[f"evidence:{e}" for e in sorted(evidence_types)],
    ]
    text = f"{outcome.title()} a '{cat.replace('_', ' ')}' dispute for {dispute.get('product_sku')} shipped by {dispute.get('courier')}."
    # One case per dispute: reporting the same outcome again (retry, duplicate webhook) changes nothing.
    store.retain(
        seller,
        text,
        kind="case",
        tags=tags,
        event_date=closed,
        memory_id=f"outcome_{dispute['id']}",
    )
    after = compute_beliefs(load_cases(store, seller), dismissed)
    changes = belief_changes(before, after)
    stamp = datetime.now(UTC).isoformat()
    CHANGE_LOG.extend({**c, "at": stamp, "dispute_id": dispute["id"]} for c in changes)
    return changes


# ---- M3/M7: learning from edits (proposals only; the seller confirms before anything is saved) ----


def propose_directives(
    before: str, after: str, decision: str | None = None, amount: int | None = None
) -> list[dict]:
    props = []
    if re.search(r"return policy|refund policy", after, re.I) and not re.search(
        r"return policy|refund policy", before, re.I
    ):
        props.append(
            {
                "text": "Always cite my return policy",
                "reason": "You added the return policy to the letter",
            }
        )
    if before and len(after) < 0.7 * len(before):
        props.append(
            {
                "text": "Keep letters short and formal",
                "reason": "You shortened the draft by more than 30%",
            }
        )
    if decision == "accept" and amount is not None and amount < 5000:
        props.append(
            {
                "text": f"Never fight disputes under {amount // 100 + 1}",
                "reason": "You accepted a small dispute",
            }
        )
    return props


# ---- M5: Seller Playbook ----


def build_playbook(
    memory: list[MemoryRef], directives: list[MemoryRef], dismissed: set[str] = frozenset()
) -> dict:
    cases = _cases(memory)
    beliefs = compute_beliefs(memory, dismissed)
    customers = Counter(
        t.split(":", 1)[1] for m in cases for t in m.tags if t.startswith("customer:")
    )
    repeat = [c for c, n in customers.items() if n >= 2]
    sections = {
        "best_evidence": [asdict(b) for b in beliefs if b.kind == "evidence"],
        "risky_couriers": [asdict(b) for b in beliefs if b.kind == "courier"],
        "repeat_disputers": [{"customer": c, "disputes": customers[c]} for c in repeat],
        "preferences": [d.text for d in directives],
        "n_cases": len(cases),
    }
    lines = [
        "# Seller Playbook",
        f"_Learned from {len(cases)} resolved disputes._",
        "",
        "## Best evidence",
    ]
    lines += [
        f"- {b['text']} - confidence {b['confidence']:.0%} ({b['label']}, n={b['n']})"
        for b in sections["best_evidence"]
    ] or ["- Not enough history yet."]
    lines += ["", "## Risky couriers"] + (
        [
            f"- {b['text']} - confidence {b['confidence']:.0%} ({b['label']})"
            for b in sections["risky_couriers"]
        ]
        or ["- None detected."]
    )
    lines += ["", "## Repeat disputers"] + (
        [f"- {r['customer']}: {r['disputes']} disputes" for r in sections["repeat_disputers"]]
        or ["- None."]
    )
    lines += ["", "## Your preferences"] + (
        [f"- {p}" for p in sections["preferences"]] or ["- None saved yet."]
    )
    return {**sections, "markdown": "\n".join(lines)}
