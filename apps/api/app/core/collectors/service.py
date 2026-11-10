"""Run a collector for a dispute and persist the result.

Collection can never lose or corrupt a dispute: the collector runs first (pure, no DB writes), and
every write happens inside a SAVEPOINT. If anything fails, only the savepoint rolls back, so the
dispute row stays and no partial evidence is left behind.

Everything a collector returns is stored `verified=true`: collectors read systems of record. A
collector that returns a seller note/claim/upload is rejected by the database CHECK constraint.
"""

import hashlib
import logging

from sqlalchemy.orm import Session

from app.core.collectors.base import DisputeContext, EvidenceCollector
from app.core.tables import DisputeRow, EvidenceRow

log = logging.getLogger(__name__)


def evidence_id(dispute_id: str, source: str, ref: str) -> str:
    """Deterministic id: re-running collection updates rows instead of duplicating them."""
    digest = hashlib.sha1(f"{dispute_id}|{source}|{ref}".encode()).hexdigest()  # noqa: S324
    return f"ev_{digest[:12]}"


def context_for(row: DisputeRow) -> DisputeContext:
    return DisputeContext(
        seller_id=row.seller_id,
        dispute_id=row.id,
        order_id=row.order_id,
        customer_hash=row.customer_hash,
        amount=row.amount,
        currency=row.currency,
        created_at=row.created_at,
        processor_charge_id=row.processor_charge_id,
    )


def collect_for_dispute(session: Session, row: DisputeRow, collector: EvidenceCollector) -> int:
    """Collect and store evidence. Returns the number of items stored (0 on failure or no match)."""
    try:
        collection = collector.collect(context_for(row))
        if not collection.items:
            return 0
        with session.begin_nested():
            for item in collection.items:
                session.merge(
                    EvidenceRow(
                        id=evidence_id(row.id, item.source, item.ref),
                        dispute_id=row.id,
                        type=item.type,
                        source=item.source,
                        verified=True,
                        summary=item.summary,
                        uri=item.uri,
                        captured_at=item.captured_at,
                    )
                )
            # Fill gaps on the dispute from the matched order; never overwrite known values.
            row.order_id = row.order_id or collection.order_id
            row.product_sku = row.product_sku or collection.product_sku
            row.courier = row.courier or collection.courier
            row.tracking_number = row.tracking_number or collection.tracking_number
            session.flush()
        return len(collection.items)
    except Exception:
        log.warning("evidence collection failed for %s", row.id, exc_info=True)
        return 0
