"""Draft review, approval, submission and acceptance (F5, F6).

Nothing leaves the system without an explicit, specific seller approval:
- approval must be explicit (`approved: true`) and carry the hash of the exact letter, sources and
  attachments the seller reviewed; if anything changed since, the seller must review again;
- every claim is re-validated here against the database (rule 5), whatever the browser sent;
- the Submission row is committed as `pending` BEFORE the processor is called, a partial unique
  index allows one live submission per dispute, and the Stripe calls carry the submission id as an
  idempotency key. `submit=true` is final, so it can never happen twice.

Honest statuses: the dispute becomes `submitted` only after the processor confirmed. A PDF export
(no key, past the deadline, unsupported processor) leaves it `approved` with a plain explanation.
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core import uploads
from app.core.errors import ApiError
from app.core.letter import (
    check_claims,
    letter_hash,
    render_final_letter,
    reserved_text_in,
)
from app.core.models import (
    AcceptRequest,
    AcceptResult,
    ApproveRequest,
    LetterPreview,
    LetterRequest,
    Submission,
)
from app.core.packet import Attachment, PacketTooLarge, build_packet
from app.core.processors import ProcessorSubmitter, SubmitError
from app.core.tables import DisputeRow, DraftRow, EvidenceRow, SubmissionRow
from app.settings import settings

log = logging.getLogger(__name__)

FINAL = {"submitted", "won", "lost", "accepted"}

# A Stripe call can stay in flight this long: SDK timeout 80 s x 2 calls x 3 attempts (2 network
# retries) = 8 minutes. A younger `pending` row may still be running, so never reconcile it.
PENDING_GRACE = timedelta(minutes=10)


# -- loading -----------------------------------------------------------------------------------
def load_dispute(session: Session, dispute_id: str, *, lock: bool = False) -> DisputeRow:
    query = select(DisputeRow).options(selectinload(DisputeRow.evidence))
    query = query.where(DisputeRow.id == dispute_id)
    if lock:
        query = query.with_for_update(of=DisputeRow)
    row = session.scalar(query)
    if row is None:
        raise ApiError(404, "not_found", f"dispute {dispute_id} not found")
    return row


def _upload_attachments(
    req: LetterRequest, evidence: dict[str, EvidenceRow]
) -> list[tuple[EvidenceRow, Attachment]]:
    found = []
    for ev_id in dict.fromkeys(req.attach_upload_ids):
        ev = evidence.get(ev_id)
        if ev is None or ev.type != "seller_upload" or not (ev.uri or "").startswith("files/"):
            raise ApiError(422, "invalid_attachment", f"{ev_id} is not one of your uploads")
        name = ev.uri.removeprefix("files/")
        path = uploads.path_for(name)
        if path is None:
            raise ApiError(422, "attachment_missing", f"the file for {ev_id} is no longer stored")
        shown = ev.summary.removeprefix("Seller upload: ")
        found.append(
            (ev, Attachment(name=shown, data=path.read_bytes(), kind=name.rsplit(".", 1)[1]))
        )
    return found


class _Prepared:
    def __init__(self, row, evidence, blocked, attachments, letter, sha):
        self.row, self.evidence, self.blocked = row, evidence, blocked
        self.attachments, self.letter, self.sha = attachments, letter, sha


def _prepare(row: DisputeRow, req: LetterRequest) -> _Prepared:
    evidence = {e.id: e for e in row.evidence}
    blocked = check_claims(req.claims, evidence)
    attachments = _upload_attachments(req, evidence)
    letter = render_final_letter(req.claims, req.seller_statement)
    sha = letter_hash(letter, req.claims, list(dict.fromkeys(req.attach_upload_ids)), evidence)
    return _Prepared(row, evidence, blocked, attachments, letter, sha)


# -- preview and draft -------------------------------------------------------------------------
def preview(session: Session, dispute_id: str, req: LetterRequest) -> LetterPreview:
    p = _prepare(load_dispute(session, dispute_id), req)
    return LetterPreview(
        letter_md=p.letter,
        letter_sha256=p.sha,
        blocked=p.blocked,
        attachments=[a.name for _, a in p.attachments],
    )


def save_draft(session: Session, dispute_id: str, req: LetterRequest, memory_mode: str) -> str:
    row = load_dispute(session, dispute_id, lock=True)
    if row.status in FINAL:
        raise ApiError(409, "already_final", f"dispute is already {row.status}")
    session.merge(
        DraftRow(
            id=f"dr_{dispute_id}",
            dispute_id=dispute_id,
            memory_mode=memory_mode,
            payload=req.model_dump(),
        )
    )
    if row.status == "needs_response":
        row.status = "drafted"
    session.commit()
    return row.status


def saved_draft(session: Session, dispute_id: str) -> dict | None:
    draft = session.get(DraftRow, f"dr_{dispute_id}")
    return None if draft is None else {**draft.payload, "memory_mode": draft.memory_mode}


# -- approve and submit ------------------------------------------------------------------------
def resolve_submitter(submitter: ProcessorSubmitter, processor: str) -> ProcessorSubmitter | None:
    """MultiSubmitter picks by processor; a plain submitter (tests) is treated as Stripe-only."""
    pick = getattr(submitter, "for_processor", None)
    if pick is not None:
        return pick(processor)
    return submitter if processor == "stripe" else None


def _reconcile_pending(
    session: Session, row: DisputeRow, submitter: ProcessorSubmitter, now: datetime
) -> None:
    """A `pending` submission means an attempt has not recorded its result. If it is young it may
    still be running: refuse. If it is old, find out whether the processor already has it before
    allowing another attempt."""
    pending = session.scalar(
        select(SubmissionRow).where(
            SubmissionRow.dispute_id == row.id, SubmissionRow.status == "pending"
        )
    )
    if pending is None:
        return
    if pending.created_at > now - PENDING_GRACE:
        raise ApiError(
            409,
            "submission_in_progress",
            "a response is already being submitted; wait for it to finish",
        )
    submitted = False
    active = resolve_submitter(submitter, row.processor)
    if active is not None and active.available()[0]:
        try:
            submitted = active.is_submitted(row.processor_dispute_id)
        except SubmitError as exc:
            raise ApiError(
                502, "processor_error", f"could not check the earlier attempt: {exc.message}"
            ) from exc
    if submitted:
        pending.status, pending.submitted_at = "submitted", datetime.now(UTC)
        row.status = "submitted"
        session.commit()
        raise ApiError(409, "already_submitted", "an earlier attempt had already been submitted")
    pending.status, pending.error = "failed", "interrupted before it completed"
    session.flush()


def _audit(req: LetterRequest, prepared: _Prepared, pages: int, size: int, packet) -> dict:
    originals: dict[str, list[str]] = {}
    for c in req.agent_claims or []:
        originals.setdefault(c.evidence_id, []).append(c.text)
    claims = []
    for c in req.claims:
        agent_texts = originals.get(c.evidence_id, [])
        claims.append(
            {
                "text": c.text,
                "evidence_id": c.evidence_id,
                "edited": c.text not in agent_texts,
                "agent_text": agent_texts[0] if agent_texts else None,
            }
        )
    return {
        # `agent_claims` is reported by the browser, so these flags are not ground truth.
        "audit_source": "client_reported",
        "claims": claims,
        "seller_statement": (req.seller_statement or "").strip() or None,
        "attachments": [a.name for _, a in prepared.attachments],
        "not_embedded": packet.not_embedded,
        "pages": pages,
        "bytes": size,
    }


def approve(
    session: Session,
    dispute_id: str,
    req: ApproveRequest,
    submitter: ProcessorSubmitter,
    *,
    now: datetime | None = None,
) -> Submission:
    now = now or datetime.now(UTC)
    if not req.approved:
        raise ApiError(422, "not_approved", "approval must be explicit")
    row = load_dispute(session, dispute_id, lock=True)
    if row.status in FINAL:
        raise ApiError(409, "already_final", f"dispute is already {row.status}")
    _reconcile_pending(session, row, submitter, now)

    if not req.claims:
        raise ApiError(422, "no_claims", "a response needs at least one claim backed by evidence")
    prepared = _prepare(row, req)
    if prepared.blocked:
        listing = "; ".join(f"claim {b.index + 1}: {b.reason}" for b in prepared.blocked)
        raise ApiError(422, "unsourced_claims", listing)
    reserved = reserved_text_in(*(c.text for c in req.claims), req.seller_statement)
    if reserved:
        raise ApiError(422, "reserved_text", f"'{reserved}' cannot appear in a response")
    if prepared.sha != req.letter_sha256:
        raise ApiError(
            409, "stale_review", "the letter, sources or attachments changed; review it again"
        )

    try:
        packet = build_packet(
            dispute=row,
            letter_md=prepared.letter,
            claims=req.claims,
            evidence=prepared.evidence,
            attachments=[a for _, a in prepared.attachments],
        )
    except PacketTooLarge as exc:
        raise ApiError(422, "packet_too_large", str(exc)) from exc

    active = resolve_submitter(submitter, row.processor)
    if active is not None:
        can_send, why = active.available()
    else:
        can_send, why = False, f"{row.processor} disputes cannot be submitted automatically yet"
    overdue = row.deadline_at <= now
    send = can_send and not overdue
    note = None
    if overdue:
        note = (
            "The response deadline has passed, so nothing was sent. "
            "Download the PDF and upload it yourself if the processor still accepts it."
        )
    elif not can_send:
        note = f"Not sent automatically: {why}. Download the PDF and upload it in your dashboard."

    sub_id = "sub_" + secrets.token_hex(6)
    pdf_dir = settings.upload_dir / "packets"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / f"{sub_id}.pdf").write_bytes(packet.pdf)

    sub = SubmissionRow(
        id=sub_id,
        dispute_id=row.id,
        draft_id=None,
        letter_md=prepared.letter,
        status="pending" if send else "exported",
        approved_at=now,
        letter_sha256=prepared.sha,
        note=note,
        detail=_audit(req, prepared, packet.pages, len(packet.pdf), packet),
        pdf_uri=f"packets/{sub_id}.pdf",
    )
    session.add(sub)
    if not send:
        row.status = "approved"
    try:
        session.commit()  # the pending row exists before the processor is ever called
    except IntegrityError as exc:
        session.rollback()
        (pdf_dir / f"{sub_id}.pdf").unlink(missing_ok=True)
        raise ApiError(
            409, "submission_in_progress", "a response is already being submitted"
        ) from exc
    if not send:
        return to_submission(sub)

    try:
        assert active is not None  # send is only True when a submitter is available
        active.submit(
            processor_dispute_id=row.processor_dispute_id,
            idempotency_key=sub_id,
            letter_text=prepared.letter,
            packet_pdf=packet.pdf,
            shipping_carrier=row.courier,
            tracking_number=row.tracking_number,
            category=row.category,
        )
    except SubmitError as exc:
        _mark_failed(session, row, sub, f"{exc.code}: {exc.message}")
        return to_submission(sub)
    except Exception as exc:  # never leave a submission pending after an unexpected failure
        log.exception("unexpected error submitting %s", sub_id)
        _mark_failed(session, row, sub, f"unexpected_error: {type(exc).__name__}")
        return to_submission(sub)

    sub.status, sub.submitted_at = "submitted", datetime.now(UTC)
    row.status = "submitted"
    session.commit()
    return to_submission(sub)


def _mark_failed(session: Session, row: DisputeRow, sub: SubmissionRow, error: str) -> None:
    sub.status, sub.error = "failed", error
    row.status = "approved"  # the seller approved it; it was not sent
    session.commit()


# -- accept ------------------------------------------------------------------------------------
def accept(
    session: Session, dispute_id: str, req: AcceptRequest, submitter: ProcessorSubmitter
) -> AcceptResult:
    if not req.confirm:
        raise ApiError(422, "not_confirmed", "accepting a dispute needs explicit confirmation")
    row = load_dispute(session, dispute_id, lock=True)
    if row.status in FINAL:
        raise ApiError(409, "already_final", f"dispute is already {row.status}")
    # Never close the dispute while a submission may still be running.
    _reconcile_pending(session, row, submitter, datetime.now(UTC))

    closed = False
    active = resolve_submitter(submitter, row.processor)
    if active is not None:
        can_close, why = active.available()
    else:
        can_close, why = False, f"{row.processor} disputes cannot be closed automatically yet"
    if can_close:
        try:
            assert active is not None
            active.close(row.processor_dispute_id)
            closed = True
        except SubmitError as exc:
            raise ApiError(502, "processor_error", f"{exc.code}: {exc.message}") from exc
    row.status = "accepted"
    session.commit()
    note = (
        "Accepted and closed with the processor."
        if closed
        else f"Recorded as accepted here, but NOT closed with the processor ({why}). "
        "Close it in your processor dashboard."
    )
    return AcceptResult(status="accepted", closed_at_processor=closed, note=note)


# -- reading -----------------------------------------------------------------------------------
def to_submission(row: SubmissionRow) -> Submission:
    return Submission(
        id=row.id,
        dispute_id=row.dispute_id,
        draft_id=row.draft_id,
        letter_md=row.letter_md,
        status=row.status,
        approved_at=row.approved_at,
        submitted_at=row.submitted_at,
        pdf_uri=row.pdf_uri,
        error=row.error,
        note=row.note,
    )


def latest_submission(session: Session, dispute_id: str) -> Submission | None:
    row = session.scalar(
        select(SubmissionRow)
        .where(SubmissionRow.dispute_id == dispute_id)
        .order_by(SubmissionRow.created_at.desc(), SubmissionRow.id.desc())
        .limit(1)
    )
    return None if row is None else to_submission(row)
