"""Helpers for Phase 4 tests: a recording fake processor, real image/PDF bytes, a fresh dispute."""

import io
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF
from PIL import Image

from app.core.processors import SubmitError
from app.core.router import get_submitter
from app.core.tables import DisputeRow, EvidenceRow, SellerRow
from app.main import app
from app.settings import settings


class FakeSubmitter:
    """Records every call; can be told to be unavailable, fail, or report an earlier submission."""

    def __init__(self) -> None:
        self.ok, self.why = True, ""
        self.fail: SubmitError | None = None
        self.close_fail: SubmitError | None = None
        self.already_submitted = False
        self.submits: list[dict] = []
        self.closes: list[str] = []

    def available(self) -> tuple[bool, str]:
        return self.ok, self.why

    def is_submitted(self, processor_dispute_id: str) -> bool:
        return self.already_submitted

    def submit(self, **kwargs) -> None:
        self.submits.append(kwargs)
        if self.fail:
            raise self.fail

    def close(self, processor_dispute_id: str) -> None:
        if self.close_fail:
            raise self.close_fail
        self.closes.append(processor_dispute_id)


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "PNG")
    return buf.getvalue()


def jpg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "JPEG")
    return buf.getvalue()


def pdf_bytes(text: str = "Seller document", pages: int = 1) -> bytes:
    pdf = FPDF()
    for _ in range(pages):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, text)
    return bytes(pdf.output())


FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # passes the magic-byte check, not a real image


def add_dispute(
    session, dispute_id="dp_t1", *, deadline_in=timedelta(days=5), status="needs_response"
):
    if session.get(SellerRow, "sel_demo") is None:
        session.add(
            SellerRow(id="sel_demo", name="Demo seller", processor="stripe", currency="usd")
        )
        session.flush()
    now = datetime.now(UTC)
    session.add(
        DisputeRow(
            id=dispute_id,
            seller_id="sel_demo",
            processor="stripe",
            processor_dispute_id=f"du_{dispute_id}",
            amount=12900,
            currency="usd",
            reason_raw="product_not_received",
            category="not_received",
            status=status,
            created_at=now - timedelta(days=2),
            deadline_at=now + deadline_in,
            customer_hash="c_test",
            courier="CourierX",
        )
    )
    session.flush()
    at = now - timedelta(days=10)
    for ev_id, type_, source, verified, summary in (
        (
            "ev_a",
            "delivery_proof",
            "shipping_api",
            True,
            "Delivered 2026-09-16 13:42, signed by B. H.",
        ),
        ("ev_b", "order_receipt", "shop_api", True, "Order ord_101: Logo Tee, $49.99 (EUR check)"),
        ("ev_note", "seller_note", "seller_claim", False, "Customer said a neighbour took it"),
    ):
        session.add(
            EvidenceRow(
                id=f"{dispute_id}_{ev_id}" if dispute_id != "dp_t1" else ev_id,
                dispute_id=dispute_id,
                type=type_,
                source=source,
                verified=verified,
                summary=summary,
                captured_at=at,
            )
        )
    session.commit()


def add_upload(
    session, tmp_uploads, name: str, data: bytes, ev_id: str, shown: str, dispute="dp_t1"
):
    tmp_uploads.mkdir(parents=True, exist_ok=True)
    (tmp_uploads / name).write_bytes(data)
    session.add(
        EvidenceRow(
            id=ev_id,
            dispute_id=dispute,
            type="seller_upload",
            source="seller_upload",
            verified=False,
            summary=f"Seller upload: {shown}",
            uri=f"files/{name}",
            captured_at=datetime.now(UTC),
        )
    )
    session.commit()


@pytest.fixture
def env(session, tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(settings, "upload_dir", uploads)
    fake = FakeSubmitter()
    app.dependency_overrides[get_submitter] = lambda: fake
    add_dispute(session)
    yield SimpleNamespace(session=session, fake=fake, client=TestClient(app), uploads=uploads)
    app.dependency_overrides.clear()


CLAIMS = [
    {"text": "The parcel was delivered on 16 Sep and signed for.", "evidence_id": "ev_a"},
    {"text": "The order was placed and paid in full.", "evidence_id": "ev_b"},
]


def letter_request(claims=None, statement=None, attach=None, agent_claims=None) -> dict:
    body = {
        "claims": CLAIMS if claims is None else claims,
        "seller_statement": statement,
        "attach_upload_ids": attach or [],
    }
    if agent_claims is not None:
        body["agent_claims"] = agent_claims
    return body


def approve_body(env, dispute="dp_t1", **kwargs) -> dict:
    req = letter_request(**kwargs)
    preview = env.client.post(f"/core/disputes/{dispute}/letter-preview", json=req).json()
    return {**req, "approved": True, "letter_sha256": preview["letter_sha256"]}
