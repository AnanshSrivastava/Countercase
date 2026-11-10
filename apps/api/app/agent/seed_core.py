# ruff: noqa: E501
"""Load data/seed/history.json (SYNTHETIC) into core's tables as resolved disputes, for the insights dashboard.

    python -m app.agent.seed_core            (uses DATABASE_URL / settings.database_url)

Idempotent. Rows get ids hist_NNN and processor ids du_hist_NNN, so they never collide with live disputes
or the dp_00N fixtures. Everything is marked verified only where a system would have pulled it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import session_factory
from app.core.disputes import ensure_seller
from app.core.tables import DisputeRow, EvidenceRow

HISTORY = Path(__file__).resolve().parents[4] / "data" / "seed" / "history.json"

REASON_RAW = {
    "not_received": "product_not_received",
    "unauthorized": "fraudulent",
    "not_as_described": "product_unacceptable",
    "refund_not_processed": "credit_not_processed",
    "duplicate": "duplicate",
}
# generator evidence name -> (contract EvidenceType, source)
EVIDENCE = {
    "order_receipt": ("order_receipt", "shop_api"),
    "tracking": ("tracking", "shipping_api"),
    "delivery_photo": ("delivery_proof", "shipping_api"),
    "signature": ("delivery_proof", "shipping_api"),
    "prior_orders": ("prior_orders", "shop_api"),
    "ip_device": ("ip_device", "shop_api"),
    "refund_policy": ("refund_policy", "shop_api"),
    "customer_message": ("customer_message", "shop_api"),
}


def _ts(day: str, hour: int = 12) -> datetime:
    return datetime.combine(datetime.fromisoformat(day).date(), time(hour), tzinfo=UTC)


def seed_history(session: Session, history: dict) -> int:
    ensure_seller(session, history["seller_id"])
    for c in history["cases"]:
        created = _ts(c["created"])
        n = c["id"].split("_", 1)[1]
        session.merge(
            DisputeRow(
                id=c["id"],
                seller_id=history["seller_id"],
                processor="stripe",
                processor_dispute_id=f"du_hist_{n}",
                amount=c["amount"],
                currency=c["currency"],
                reason_raw=REASON_RAW[c["category"]],
                category=c["category"],
                status=c["outcome"],  # won | lost | accepted
                created_at=created,
                deadline_at=created + timedelta(days=7),
                customer_hash=c["customer"],
                order_id=f"ord_hist_{n}",
                product_sku=c["sku"],
                courier=c["courier"],
                last_event_at=_ts(c["resolved"]),
            )
        )
        session.flush()
        seen: set[str] = set()
        for e in c["evidence"]:
            etype, source = EVIDENCE[e]
            if etype in seen:  # photo and signature both map to delivery_proof
                continue
            seen.add(etype)
            session.merge(
                EvidenceRow(
                    id=f"ev_{c['id']}_{etype}",
                    dispute_id=c["id"],
                    type=etype,
                    source=source,
                    verified=True,
                    summary=f"{etype.replace('_', ' ').title()} (synthetic history)",
                    uri=None,
                    captured_at=created,
                )
            )
    session.commit()
    return len(history["cases"])


if __name__ == "__main__":
    with session_factory()() as s:
        print(
            f"seeded {seed_history(s, json.loads(HISTORY.read_text(encoding='utf-8')))} historical disputes"
        )
