"""Demo reset: guarded, keeps seeded history, recreates collected demo disputes."""

import pytest

from app.core import demo_reset
from app.core.disputes import seed_fixtures
from app.core.tables import DisputeRow, EvidenceRow, SellerRow
from app.settings import settings

from .p4_helpers import add_dispute, add_upload, png_bytes


def ids(session) -> set[str]:
    session.expire_all()
    return {d.id for d in session.query(DisputeRow).all()}


def test_refuses_unless_demo_tools_are_on(session) -> None:
    add_dispute(session)
    with pytest.raises(PermissionError):
        demo_reset.reset(session)
    assert "dp_t1" in ids(session)  # nothing was deleted


def test_wipes_live_data_keeps_history_and_recreates_demo_disputes(
    session, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "demo_tools", True)
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    add_dispute(session)
    add_upload(session, tmp_path / "uploads", "a" * 32 + ".png", png_bytes(), "ev_up", "x.png")
    seed_fixtures(session)  # live fixtures (not hist_*) are wiped too
    session.add(
        DisputeRow(
            id="hist_001",
            seller_id="sel_demo",
            processor="stripe",
            processor_dispute_id="du_hist_001",
            amount=1000,
            currency="usd",
            reason_raw="x",
            status="won",
            created_at=session.get(DisputeRow, "dp_t1").created_at,
            deadline_at=session.get(DisputeRow, "dp_t1").deadline_at,
            customer_hash="c_h",
        )
    )
    session.commit()

    assert demo_reset.reset(session) == 3

    after = ids(session)
    assert "hist_001" in after  # seeded history untouched
    assert not ({"dp_t1", "dp_001", "dp_002", "dp_003"} & after)  # live data wiped
    assert len(after) == 4  # hist + 3 demo disputes
    assert not (tmp_path / "uploads").exists()  # uploaded files removed
    assert session.get(SellerRow, "sel_demo") is not None


def test_demo_disputes_get_evidence_and_the_expected_shape(session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_tools", True)
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    demo_reset.reset(session)
    session.expire_all()
    by_order = {d.order_id: d for d in session.query(DisputeRow).all()}
    assert set(by_order) == {"ord_101", "ord_102", "ord_103"}
    counts = {
        o: session.query(EvidenceRow).filter_by(dispute_id=d.id).count()
        for o, d in by_order.items()
    }
    assert counts == {"ord_101": 6, "ord_102": 6, "ord_103": 4}
    assert all(d.status == "needs_response" for d in by_order.values())


def test_reset_is_repeatable(session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_tools", True)
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    demo_reset.reset(session)
    demo_reset.reset(session)
    assert session.query(DisputeRow).count() == 3
