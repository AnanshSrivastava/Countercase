# ruff: noqa: E501
"""Tell the agent how a REAL dispute ended (Stripe `charge.dispute.closed` -> won/lost).

Runs after the webhook response (FastAPI background task), never inside the webhook transaction: the agent
may call Hindsight (an LLM) to retain the case, and a slow memory write must not delay or fail Stripe's
delivery. Safe to repeat: the agent keeps one case per dispute. Simulated demo outcomes are skipped here
because the demo tool already reports them (`processor_status` starts with `simulated:`).
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from app.core.db import session_factory
from app.core.tables import DisputeRow, EvidenceRow

log = logging.getLogger(__name__)


def report_closed(processor_dispute_id: str) -> str:
    """Returns a short label for logs and tests: reported | skipped | failed."""
    try:
        from app.agent.beliefs import record_outcome
        from app.agent.router import get_store

        with session_factory()() as session:
            row = session.scalar(
                select(DisputeRow).where(DisputeRow.processor_dispute_id == processor_dispute_id)
            )
            if row is None or row.status not in ("won", "lost"):
                return "skipped"
            if (row.processor_status or "").startswith("simulated:"):
                return "skipped"
            types = set(
                session.scalars(
                    select(EvidenceRow.type).where(
                        EvidenceRow.dispute_id == row.id, EvidenceRow.verified.is_(True)
                    )
                )
            )
            dispute = {
                "id": row.id,
                "seller_id": row.seller_id,
                "category": row.category or "other",
                "courier": row.courier,
                "product_sku": row.product_sku,
                "customer_hash": row.customer_hash,
            }
            closed = (
                (row.last_event_at or row.updated_at).date() if row.updated_at else date.today()
            )
            outcome = row.status
        record_outcome(get_store(), dispute, types, outcome, closed)
        return "reported"
    except Exception:  # noqa: BLE001 - best effort by design; the dispute is already saved
        log.exception("could not report outcome to the agent for %s", processor_dispute_id)
        return "failed"
