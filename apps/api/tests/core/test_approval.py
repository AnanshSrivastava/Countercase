"""Approval, submission and acceptance: the safety rules around an irreversible action."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.processors import SubmitError
from app.core.tables import DisputeRow, EvidenceRow, SubmissionRow

from .p4_helpers import (
    CLAIMS,
    FAKE_PNG,
    add_dispute,
    add_upload,
    approve_body,
    jpg_bytes,
    letter_request,
    pdf_bytes,
    png_bytes,
)


def dispute_status(env, dispute="dp_t1") -> str:
    env.session.expire_all()
    return env.session.get(DisputeRow, dispute).status


def pdf_text(env, sub_id: str) -> str:
    resp = env.client.get(f"/core/submissions/{sub_id}/pdf")
    assert resp.status_code == 200
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(resp.content)).pages)


# -- preview -----------------------------------------------------------------------------------
def test_preview_renders_the_agent_letter_format_and_a_stable_hash(env) -> None:
    req = letter_request()
    first = env.client.post("/core/disputes/dp_t1/letter-preview", json=req).json()
    again = env.client.post("/core/disputes/dp_t1/letter-preview", json=req).json()
    assert first == again
    assert first["letter_md"].startswith("To the dispute review team,\n\n")
    assert "The parcel was delivered on 16 Sep and signed for. [1]" in first["letter_md"]
    assert first["letter_md"].endswith("Sources: [1] ev_a, [2] ev_b.")
    assert first["blocked"] == []


def test_editing_a_claim_changes_the_hash(env) -> None:
    a = env.client.post("/core/disputes/dp_t1/letter-preview", json=letter_request()).json()
    edited = [{**CLAIMS[0], "text": "Delivered and signed for."}, CLAIMS[1]]
    b = env.client.post(
        "/core/disputes/dp_t1/letter-preview", json=letter_request(claims=edited)
    ).json()
    assert a["letter_sha256"] != b["letter_sha256"]


def test_preview_reports_blocked_claims_without_failing(env) -> None:
    claims = [
        {"text": "From a note.", "evidence_id": "ev_note"},
        {"text": "From nowhere.", "evidence_id": "ev_missing"},
        CLAIMS[0],
    ]
    out = env.client.post(
        "/core/disputes/dp_t1/letter-preview", json=letter_request(claims=claims)
    ).json()
    assert [(b["index"], b["evidence_id"]) for b in out["blocked"]] == [
        (0, "ev_note"),
        (1, "ev_missing"),
    ]


def test_seller_statement_is_labelled_not_evidence(env) -> None:
    out = env.client.post(
        "/core/disputes/dp_t1/letter-preview",
        json=letter_request(statement="Customer is a repeat buyer."),
    ).json()
    assert "Statement from the seller (not independently verified evidence):" in out["letter_md"]
    assert out["letter_md"].rstrip().endswith("Customer is a repeat buyer.")


# -- approve: the happy path -------------------------------------------------------------------
def test_approve_submits_once_with_the_right_payload(env) -> None:
    resp = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env))
    assert resp.status_code == 200
    sub = resp.json()
    assert sub["status"] == "submitted" and sub["error"] is None and sub["note"] is None
    assert dispute_status(env) == "submitted"

    [call] = env.fake.submits
    assert call["processor_dispute_id"] == "du_dp_t1"
    assert call["idempotency_key"] == sub["id"]
    assert call["shipping_carrier"] == "CourierX"
    assert call["letter_text"] == sub["letter_md"]
    assert call["packet_pdf"].startswith(b"%PDF")

    text = pdf_text(env, sub["id"])
    assert "The parcel was delivered on 16 Sep" in text
    assert "Delivered 2026-09-16 13:42, signed by B. H." in text  # source printed verbatim
    assert "verified record" in text


def test_approved_submission_is_visible_and_the_dispute_is_then_final(env) -> None:
    sub = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    assert env.client.get("/core/disputes/dp_t1/submission").json()["id"] == sub["id"]
    again = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env))
    assert again.status_code == 409 and again.json()["error"] == "already_final"
    assert len(env.fake.submits) == 1


def test_edit_audit_records_what_the_seller_changed(env) -> None:
    edited = [{**CLAIMS[0], "text": "Delivered and signed for."}, CLAIMS[1]]
    body = approve_body(env, claims=edited, agent_claims=CLAIMS)
    sub = env.client.post("/core/disputes/dp_t1/approve", json=body).json()
    env.session.expire_all()
    detail = env.session.get(SubmissionRow, sub["id"]).detail
    assert [(c["evidence_id"], c["edited"]) for c in detail["claims"]] == [
        ("ev_a", True),
        ("ev_b", False),
    ]
    assert detail["claims"][0]["agent_text"] == CLAIMS[0]["text"]


# -- approve: refusals -------------------------------------------------------------------------
def test_approval_must_be_explicit(env) -> None:
    body = {**approve_body(env), "approved": False}
    resp = env.client.post("/core/disputes/dp_t1/approve", json=body)
    assert resp.status_code == 422 and resp.json()["error"] == "not_approved"
    assert env.fake.submits == []


def test_stale_review_is_rejected(env) -> None:
    body = approve_body(env)
    body["claims"] = [{**CLAIMS[0], "text": "Changed after the preview."}, CLAIMS[1]]
    resp = env.client.post("/core/disputes/dp_t1/approve", json=body)
    assert resp.status_code == 409 and resp.json()["error"] == "stale_review"
    assert env.fake.submits == []


@pytest.mark.parametrize(
    "bad",
    [
        {"text": "From a seller note.", "evidence_id": "ev_note"},
        {"text": "Unknown source.", "evidence_id": "ev_nope"},
        {"text": "Another dispute's evidence.", "evidence_id": "dp_t2_ev_a"},
    ],
    ids=["seller-note", "unknown", "other-dispute"],
)
def test_unsourced_claims_are_refused_whatever_the_browser_sent(env, bad) -> None:
    add_dispute(env.session, "dp_t2")
    body = approve_body(env, claims=[CLAIMS[0], bad])
    resp = env.client.post("/core/disputes/dp_t1/approve", json=body)
    assert resp.status_code == 422 and resp.json()["error"] == "unsourced_claims"
    assert env.fake.submits == []
    assert env.session.scalar(select(SubmissionRow)) is None


def test_a_response_needs_at_least_one_claim(env) -> None:
    body = approve_body(env, claims=[], statement="Only my word.")
    resp = env.client.post("/core/disputes/dp_t1/approve", json=body)
    assert resp.status_code == 422 and resp.json()["error"] == "no_claims"


@pytest.mark.parametrize("word", ["winning_evidence", "losing_evidence"])
def test_stripe_test_mode_magic_words_are_refused(env, word) -> None:
    body = approve_body(env, statement=f"please {word}")
    resp = env.client.post("/core/disputes/dp_t1/approve", json=body)
    assert resp.status_code == 422 and resp.json()["error"] == "reserved_text"


def test_unknown_dispute(env) -> None:
    resp = env.client.post("/core/disputes/dp_nope/approve", json=approve_body(env))
    assert resp.status_code == 404


# -- export instead of submit ------------------------------------------------------------------
def test_overdue_dispute_is_exported_not_sent(env) -> None:
    add_dispute(env.session, "dp_late", deadline_in=timedelta(hours=-3))
    claims = [{"text": "Delivered.", "evidence_id": "dp_late_ev_a"}]
    body = approve_body(env, dispute="dp_late", claims=claims)
    sub = env.client.post("/core/disputes/dp_late/approve", json=body).json()
    assert sub["status"] == "exported" and "deadline has passed" in sub["note"]
    assert env.fake.submits == []
    assert dispute_status(env, "dp_late") == "approved"
    assert pdf_text(env, sub["id"])


def test_missing_stripe_key_exports_with_a_plain_reason(env) -> None:
    env.fake.ok, env.fake.why = False, "no Stripe test key is configured"
    sub = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    assert sub["status"] == "exported"
    assert "no Stripe test key is configured" in sub["note"]
    assert env.fake.submits == []
    assert dispute_status(env) == "approved"  # approved, NOT submitted


def test_failed_submission_keeps_the_error_and_can_be_retried(env) -> None:
    env.fake.fail = SubmitError("dispute_evidence_page_limit_exceeded", "too many pages")
    sub = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    assert sub["status"] == "failed" and "too many pages" in sub["error"]
    assert dispute_status(env) == "approved"

    env.fake.fail = None
    retry = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    assert retry["status"] == "submitted" and retry["id"] != sub["id"]
    assert dispute_status(env) == "submitted"
    assert [c["idempotency_key"] for c in env.fake.submits] == [sub["id"], retry["id"]]


def test_unexpected_processor_error_never_leaves_a_pending_submission(env) -> None:
    class Boom(Exception):
        pass

    def explode(**_):
        raise Boom()

    env.fake.submit = explode
    sub = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    assert sub["status"] == "failed" and "unexpected_error" in sub["error"]


# -- double submit protection ------------------------------------------------------------------
def test_database_allows_only_one_live_submission_per_dispute(env) -> None:
    def new(sub_id, status):
        return SubmissionRow(
            id=sub_id,
            dispute_id="dp_t1",
            letter_md="x",
            status=status,
            approved_at=datetime.now(UTC),
        )

    env.session.add(new("sub_000000000001", "pending"))
    env.session.commit()
    env.session.add(new("sub_000000000002", "submitted"))
    with pytest.raises(IntegrityError):
        env.session.commit()
    env.session.rollback()
    env.session.add(new("sub_000000000003", "failed"))  # failed/exported rows do not count
    env.session.commit()


def test_pending_from_a_crashed_attempt_that_reached_stripe_is_reconciled(env) -> None:
    env.session.add(
        SubmissionRow(
            id="sub_00000000aaaa",
            dispute_id="dp_t1",
            letter_md="x",
            status="pending",
            approved_at=datetime.now(UTC),
            created_at=datetime.now(UTC) - timedelta(minutes=30),
        )
    )
    env.session.commit()
    env.fake.already_submitted = True
    resp = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env))
    assert resp.status_code == 409 and resp.json()["error"] == "already_submitted"
    assert env.fake.submits == []  # never submitted a second time
    assert dispute_status(env) == "submitted"


def test_pending_that_never_reached_stripe_is_marked_failed_and_replaced(env) -> None:
    env.session.add(
        SubmissionRow(
            id="sub_00000000bbbb",
            dispute_id="dp_t1",
            letter_md="x",
            status="pending",
            approved_at=datetime.now(UTC),
            created_at=datetime.now(UTC) - timedelta(minutes=30),
        )
    )
    env.session.commit()
    sub = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    assert sub["status"] == "submitted"
    env.session.expire_all()
    assert env.session.get(SubmissionRow, "sub_00000000bbbb").status == "failed"


# -- attachments -------------------------------------------------------------------------------
def test_seller_attachments_are_included_and_labelled(env) -> None:
    add_upload(env.session, env.uploads, "a" * 32 + ".png", png_bytes(), "ev_up_png", "parcel.png")
    add_upload(env.session, env.uploads, "b" * 32 + ".jpg", jpg_bytes(), "ev_up_jpg", "door.jpg")
    add_upload(
        env.session,
        env.uploads,
        "c" * 32 + ".pdf",
        pdf_bytes("RECEIPT-FROM-SELLER"),
        "ev_up_pdf",
        "receipt.pdf",
    )
    body = approve_body(env, attach=["ev_up_png", "ev_up_jpg", "ev_up_pdf"])
    sub = env.client.post("/core/disputes/dp_t1/approve", json=body).json()
    assert sub["status"] == "submitted"

    text = pdf_text(env, sub["id"])
    assert "Attachment 1: parcel.png" in text and "Attachment 3: receipt.pdf" in text
    assert text.count("Provided by the seller. Not independently verified by the system.") == 3
    assert "RECEIPT-FROM-SELLER" in text  # the PDF's own pages were appended
    env.session.expire_all()
    detail = env.session.get(SubmissionRow, sub["id"]).detail
    assert detail["attachments"] == ["parcel.png", "door.jpg", "receipt.pdf"]
    assert detail["not_embedded"] == []


def test_attachment_order_puts_each_pdf_after_its_own_divider(env) -> None:
    add_upload(
        env.session, env.uploads, "a" * 32 + ".pdf", pdf_bytes("FIRST-PDF"), "ev_1", "one.pdf"
    )
    add_upload(
        env.session, env.uploads, "b" * 32 + ".pdf", pdf_bytes("SECOND-PDF"), "ev_2", "two.pdf"
    )
    sub = env.client.post(
        "/core/disputes/dp_t1/approve", json=approve_body(env, attach=["ev_1", "ev_2"])
    ).json()
    text = pdf_text(env, sub["id"])
    assert text.index("Attachment 1: one.pdf") < text.index("FIRST-PDF")
    assert text.index("FIRST-PDF") < text.index("Attachment 2: two.pdf") < text.index("SECOND-PDF")


def test_unreadable_attachment_is_listed_not_fatal(env) -> None:
    add_upload(env.session, env.uploads, "d" * 32 + ".png", FAKE_PNG, "ev_bad", "broken.png")
    add_upload(
        env.session, env.uploads, "e" * 32 + ".pdf", b"%PDF-1.4 garbage", "ev_badpdf", "bad.pdf"
    )
    sub = env.client.post(
        "/core/disputes/dp_t1/approve", json=approve_body(env, attach=["ev_bad", "ev_badpdf"])
    ).json()
    assert sub["status"] == "submitted"
    env.session.expire_all()
    assert env.session.get(SubmissionRow, sub["id"]).detail["not_embedded"] == [
        "broken.png",
        "bad.pdf",
    ]
    assert "could not be embedded" in pdf_text(env, sub["id"])


def test_only_your_own_uploads_can_be_attached(env) -> None:
    # ev_a is a verified system record, not something the seller uploaded.
    req = letter_request(attach=["ev_a"])
    out = env.client.post("/core/disputes/dp_t1/letter-preview", json=req)
    assert out.status_code == 422 and out.json()["error"] == "invalid_attachment"


def test_seller_notes_are_never_sent(env) -> None:
    sub = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    assert "neighbour" not in env.fake.submits[0]["letter_text"]
    assert "neighbour" not in pdf_text(env, sub["id"])


def test_oversized_packet_is_refused_before_anything_is_sent(env, monkeypatch) -> None:
    monkeypatch.setattr("app.core.packet.MAX_PACKET_BYTES", 1000)
    resp = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env))
    assert resp.status_code == 422 and resp.json()["error"] == "packet_too_large"
    assert env.fake.submits == []
    assert not (env.uploads / "packets").exists() or not list((env.uploads / "packets").iterdir())


def test_non_latin_text_does_not_break_the_pdf(env) -> None:
    claims = [{"text": "Paid ₹4,999 — “in full” … 支付", "evidence_id": "ev_b"}]
    sub = env.client.post(
        "/core/disputes/dp_t1/approve", json=approve_body(env, claims=claims)
    ).json()
    assert sub["status"] == "submitted"
    assert "Paid Rs 4,999 - " in pdf_text(env, sub["id"])


# -- accept ------------------------------------------------------------------------------------
def test_accept_needs_confirmation(env) -> None:
    resp = env.client.post("/core/disputes/dp_t1/accept", json={"confirm": False})
    assert resp.status_code == 422 and resp.json()["error"] == "not_confirmed"
    assert dispute_status(env) == "needs_response" and env.fake.closes == []


def test_accept_closes_with_the_processor_then_records_it(env) -> None:
    out = env.client.post("/core/disputes/dp_t1/accept", json={"confirm": True}).json()
    assert out["status"] == "accepted" and out["closed_at_processor"] is True
    assert env.fake.closes == ["du_dp_t1"]
    assert dispute_status(env) == "accepted"


def test_accept_without_a_key_says_it_was_not_closed_at_the_processor(env) -> None:
    env.fake.ok, env.fake.why = False, "no Stripe test key is configured"
    out = env.client.post("/core/disputes/dp_t1/accept", json={"confirm": True}).json()
    assert out["closed_at_processor"] is False and "NOT closed" in out["note"]
    assert dispute_status(env) == "accepted"


def test_accept_failure_changes_nothing(env) -> None:
    env.fake.close_fail = SubmitError("resource_missing", "no such dispute")
    resp = env.client.post("/core/disputes/dp_t1/accept", json={"confirm": True})
    assert resp.status_code == 502 and resp.json()["error"] == "processor_error"
    assert dispute_status(env) == "needs_response"


def test_cannot_accept_or_approve_after_either(env) -> None:
    env.client.post("/core/disputes/dp_t1/accept", json={"confirm": True})
    assert env.client.post("/core/disputes/dp_t1/accept", json={"confirm": True}).status_code == 409
    resp = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env))
    assert resp.status_code == 409 and resp.json()["error"] == "already_final"


# -- draft save and PDF endpoint ---------------------------------------------------------------
def test_saving_a_draft_marks_the_dispute_drafted_and_can_be_read_back(env) -> None:
    assert env.client.get("/core/disputes/dp_t1/draft").status_code == 404
    resp = env.client.put("/core/disputes/dp_t1/draft", json=letter_request(statement="hi"))
    assert resp.json() == {"status": "drafted"}
    saved = env.client.get("/core/disputes/dp_t1/draft").json()
    assert saved["seller_statement"] == "hi" and saved["claims"] == CLAIMS
    assert dispute_status(env) == "drafted"


@pytest.mark.parametrize("name", ["../x", "sub_zz", "sub_0123456789ab", "SUB_0123456789AB"])
def test_pdf_endpoint_only_serves_known_packets(env, name) -> None:
    assert env.client.get(f"/core/submissions/{name}/pdf").status_code == 404


def test_pdf_is_served_as_a_download(env) -> None:
    sub = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    resp = env.client.get(f"/core/submissions/{sub['id']}/pdf")
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_processor_status_tells_the_ui_whether_a_response_would_be_sent(env) -> None:
    assert env.client.get("/core/processor-status").json() == {
        "can_submit": True,
        "reason": None,
        "demo_tools": False,
    }
    env.fake.ok, env.fake.why = False, "no Stripe test key is configured"
    assert env.client.get("/core/processor-status").json() == {
        "can_submit": False,
        "reason": "no Stripe test key is configured",
        "demo_tools": False,
    }


# -- a submission that may still be running (double-click / retry while Stripe is slow) --------
def add_pending(env, sub_id="sub_00000000cccc", age=timedelta(seconds=30)):
    env.session.add(
        SubmissionRow(
            id=sub_id,
            dispute_id="dp_t1",
            letter_md="x",
            status="pending",
            approved_at=datetime.now(UTC),
            created_at=datetime.now(UTC) - age,
        )
    )
    env.session.commit()


def test_a_young_pending_submission_blocks_approve_and_is_never_reconciled(env) -> None:
    add_pending(env)
    env.fake.already_submitted = False  # even though Stripe would say "not yet"
    resp = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env))
    assert resp.status_code == 409 and resp.json()["error"] == "submission_in_progress"
    assert env.fake.submits == []
    env.session.expire_all()
    assert env.session.get(SubmissionRow, "sub_00000000cccc").status == "pending"  # untouched


def test_a_young_pending_submission_blocks_accept(env) -> None:
    add_pending(env)
    resp = env.client.post("/core/disputes/dp_t1/accept", json={"confirm": True})
    assert resp.status_code == 409 and resp.json()["error"] == "submission_in_progress"
    assert env.fake.closes == []
    assert dispute_status(env) == "needs_response"


def test_an_old_pending_submission_is_reconciled_before_accept(env) -> None:
    add_pending(env, age=timedelta(minutes=30))
    env.fake.already_submitted = True
    resp = env.client.post("/core/disputes/dp_t1/accept", json={"confirm": True})
    assert resp.status_code == 409 and resp.json()["error"] == "already_submitted"
    assert env.fake.closes == []
    assert dispute_status(env) == "submitted"


def test_an_old_pending_submission_that_never_reached_the_processor_does_not_block_accept(
    env,
) -> None:
    add_pending(env, age=timedelta(minutes=30))
    out = env.client.post("/core/disputes/dp_t1/accept", json={"confirm": True}).json()
    assert out["status"] == "accepted"


# -- the approval binds to the source text, not just the source ids ---------------------------
def test_approval_is_stale_if_a_cited_record_changed_after_the_preview(env) -> None:
    body = approve_body(env)
    ev = env.session.get(EvidenceRow, "ev_a")
    ev.summary = "Delivered 2026-09-17 09:00, left at door"  # re-collected with different text
    env.session.commit()
    resp = env.client.post("/core/disputes/dp_t1/approve", json=body)
    assert resp.status_code == 409 and resp.json()["error"] == "stale_review"
    assert env.fake.submits == []


def test_audit_says_the_edit_flags_come_from_the_browser(env) -> None:
    sub = env.client.post("/core/disputes/dp_t1/approve", json=approve_body(env)).json()
    env.session.expire_all()
    assert env.session.get(SubmissionRow, sub["id"]).detail["audit_source"] == "client_reported"
