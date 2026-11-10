"""Seller notes and uploads: stored unverified, validated by content, served safely."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.disputes import seed_fixtures
from app.core.models import EvidenceItem
from app.core.tables import EvidenceRow
from app.main import app
from app.settings import settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PDF = b"%PDF-1.4\n" + b"\x00" * 32

client = TestClient(app)


@pytest.fixture
def seeded(session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    seed_fixtures(session)
    return tmp_path / "uploads"


def post(files=None, data=None, dispute="dp_001"):
    return client.post(f"/core/disputes/{dispute}/evidence", files=files, data=data)


def test_note_is_a_seller_claim_and_never_verified(seeded) -> None:
    resp = post(data={"note": "  Customer told us it was left with a neighbour.  "})
    assert resp.status_code == 201
    [item] = resp.json()
    assert (item["type"], item["source"], item["verified"]) == (
        "seller_note",
        "seller_claim",
        False,
    )
    assert item["summary"] == "Customer told us it was left with a neighbour."


def test_png_upload_is_stored_unverified_and_served(seeded) -> None:
    resp = post(files={"file": ("../../etc/passwd.png", PNG, "image/png")})
    assert resp.status_code == 201
    [item] = resp.json()
    assert (item["type"], item["source"], item["verified"]) == (
        "seller_upload",
        "seller_upload",
        False,
    )
    assert item["summary"] == "Seller upload: passwd.png"  # path parts stripped
    name = item["uri"].removeprefix("files/")
    assert len(name) == 36 and name.endswith(".png")  # 32 hex + ".png", server-generated
    assert (seeded / name).read_bytes() == PNG

    got = client.get(f"/core/{item['uri']}")
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/png"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in got.headers["content-security-policy"]
    assert got.content == PNG


def test_pdf_is_served_as_attachment(seeded) -> None:
    [item] = post(files={"file": ("receipt.pdf", PDF, "application/pdf")}).json()
    got = client.get(f"/core/{item['uri']}")
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"].startswith("attachment")


def test_file_type_comes_from_content_not_name_or_declared_type(seeded) -> None:
    [item] = post(files={"file": ("photo.png", JPG, "image/png")}).json()
    assert item["uri"].endswith(".jpg")


def test_note_and_file_together_create_two_items(seeded) -> None:
    items = post(files={"file": ("a.png", PNG, "image/png")}, data={"note": "see photo"}).json()
    assert sorted(i["type"] for i in items) == ["seller_note", "seller_upload"]


@pytest.mark.parametrize(
    ("name", "content", "status", "error"),
    [
        ("notes.png", b"just text pretending to be an image", 415, "unsupported_file_type"),
        (
            "x.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
            415,
            "unsupported_file_type",
        ),
        ("page.html", b"<html><script>alert(1)</script></html>", 415, "unsupported_file_type"),
        ("empty.png", b"", 422, "empty_file"),
    ],
)
def test_rejected_files(seeded, name, content, status, error) -> None:
    resp = post(files={"file": (name, content, "application/octet-stream")})
    assert resp.status_code == status
    assert resp.json()["error"] == error
    assert not seeded.exists() or list(seeded.iterdir()) == []


def test_oversized_file_is_rejected(seeded, monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    resp = post(files={"file": ("big.png", PNG + b"\x00" * 2048, "image/png")})
    assert resp.status_code == 413
    assert resp.json()["error"] == "file_too_large"


def test_nothing_to_add_and_long_note(seeded) -> None:
    assert post(data={"note": "   "}).json()["error"] == "nothing_to_add"
    assert post(data={"note": "x" * 2001}).json()["error"] == "note_too_long"


def test_unknown_dispute_is_404_and_leaves_no_orphan_file(seeded) -> None:
    resp = post(files={"file": ("a.png", PNG, "image/png")}, dispute="dp_nope")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"
    assert list(seeded.iterdir()) == []


@pytest.mark.parametrize(
    "name", ["../secret.png", "abc.png", "A" * 32 + ".png", "0" * 32 + ".svg", "0" * 32 + ".png"]
)
def test_file_endpoint_only_serves_names_we_generated(seeded, name) -> None:
    assert client.get(f"/core/files/{name}").status_code == 404


def test_uploads_appear_in_dispute_detail_as_unverified(seeded) -> None:
    post(data={"note": "my note"})
    evidence = client.get("/core/disputes/dp_001").json()["evidence"]
    mine = [e for e in evidence if e["summary"] == "my note"]
    assert len(mine) == 1 and mine[0]["verified"] is False


@pytest.mark.parametrize(
    ("type_", "source"),
    [
        ("seller_upload", "seller_upload"),
        ("seller_upload", "shop_api"),
        ("order_receipt", "seller_upload"),
    ],
)
def test_database_rejects_verified_seller_supplied_evidence(session, type_, source) -> None:
    seed_fixtures(session)
    session.add(
        EvidenceRow(
            id="ev_bad",
            dispute_id="dp_001",
            type=type_,
            source=source,
            verified=True,
            summary="x",
            captured_at=datetime(2026, 10, 1, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_contract_model_rejects_verified_upload() -> None:
    with pytest.raises(ValueError, match="seller-supplied"):
        EvidenceItem(
            id="e",
            dispute_id="d",
            type="seller_upload",
            source="seller_upload",
            verified=True,
            summary="x",
            uri=None,
            captured_at=datetime(2026, 10, 1, tzinfo=UTC),
        )
