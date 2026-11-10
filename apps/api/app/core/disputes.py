"""Read side of core: DB rows -> contract models, plus idempotent fixture seeding."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.models import Dispute, DisputeDetail, EvidenceItem
from app.core.tables import DisputeRow, EvidenceRow, SellerRow
from app.settings import settings


def to_dispute(row: DisputeRow) -> Dispute:
    return Dispute(
        id=row.id,
        seller_id=row.seller_id,
        processor=row.processor,
        processor_dispute_id=row.processor_dispute_id,
        amount=row.amount,
        currency=row.currency,
        reason_raw=row.reason_raw,
        category=row.category,
        category_explanation=row.category_explanation,
        status=row.status,
        created_at=row.created_at,
        deadline_at=row.deadline_at,
        customer_hash=row.customer_hash,
        order_id=row.order_id,
        product_sku=row.product_sku,
        courier=row.courier,
        evidence=[e.id for e in row.evidence],  # derived from evidence_items, never stored twice
    )


def to_evidence(row: EvidenceRow) -> EvidenceItem:
    return EvidenceItem(
        id=row.id,
        dispute_id=row.dispute_id,
        type=row.type,
        source=row.source,
        verified=row.verified,
        summary=row.summary,
        uri=row.uri,
        captured_at=row.captured_at,
    )


def list_disputes(
    session: Session, *, seller_id: str | None = None, status: str | None = None
) -> list[Dispute]:
    query = (
        select(DisputeRow)
        .options(selectinload(DisputeRow.evidence))
        .order_by(DisputeRow.deadline_at)
    )
    if seller_id:
        query = query.where(DisputeRow.seller_id == seller_id)
    if status:
        query = query.where(DisputeRow.status == status)
    return [to_dispute(r) for r in session.scalars(query)]


def get_dispute(session: Session, dispute_id: str) -> DisputeDetail | None:
    row = session.scalar(
        select(DisputeRow)
        .options(selectinload(DisputeRow.evidence))
        .where(DisputeRow.id == dispute_id)
    )
    if row is None:
        return None
    return DisputeDetail(dispute=to_dispute(row), evidence=[to_evidence(e) for e in row.evidence])


def ensure_seller(session: Session, seller_id: str, *, account_id: str | None = None) -> SellerRow:
    seller = session.get(SellerRow, seller_id)
    if seller is None:
        seller = SellerRow(
            id=seller_id, name="Demo seller", processor="stripe", processor_account_id=account_id
        )
        session.add(seller)
        session.flush()
    return seller


def seed_fixtures(session: Session, fixtures_dir: Path | None = None) -> int:
    """Upsert fixtures/disputes/*.json into the DB. Safe to repeat. Returns the dispute count."""
    directory = (fixtures_dir or settings.fixtures_dir) / "disputes"
    count = 0
    for path in sorted(directory.glob("*.json")):
        data = DisputeDetail.model_validate(json.loads(path.read_text(encoding="utf-8")))
        d = data.dispute
        ensure_seller(session, d.seller_id)
        session.merge(
            DisputeRow(
                id=d.id,
                seller_id=d.seller_id,
                processor=d.processor,
                processor_dispute_id=d.processor_dispute_id,
                amount=d.amount,
                currency=d.currency,
                reason_raw=d.reason_raw,
                category=d.category,
                status=d.status,
                created_at=d.created_at,
                deadline_at=d.deadline_at,
                customer_hash=d.customer_hash,
                order_id=d.order_id,
                product_sku=d.product_sku,
                courier=d.courier,
            )
        )
        session.flush()
        for e in data.evidence:
            session.merge(EvidenceRow(**e.model_dump()))
        count += 1
    session.commit()
    return count


if __name__ == "__main__":  # python -m app.core.disputes  (make seed-fixtures)
    from app.core.db import session_factory

    with session_factory()() as s:
        print(f"seeded {seed_fixtures(s)} fixture disputes")
