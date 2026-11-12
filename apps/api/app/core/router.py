"""Core router (owner: Lakshya). Facts only: DB, Stripe ingestion, evidence, deadlines, insights.
Endpoints follow docs/CONTRACTS.md; see docs/plans/lakshya.md for what lands in which phase.
"""

import re
import secrets
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import alerts, demo, outcome_report, stripe_ingest, submissions, uploads
from app.core.collectors import EvidenceCollector, collect_for_dispute
from app.core.db import get_session, session_factory
from app.core.disputes import get_dispute, list_disputes, to_evidence
from app.core.errors import ApiError
from app.core.insights import insights_router
from app.core.models import (
    AcceptRequest,
    AcceptResult,
    Alert,
    ApproveRequest,
    Dispute,
    DisputeDetail,
    DisputeStatus,
    EvidenceItem,
    LetterPreview,
    LetterRequest,
    Submission,
)
from app.core.paypal import ingest as paypal_ingest
from app.core.paypal.client import PayPalClient, PayPalError
from app.core.paypal.collector import PayPalCollector
from app.core.processors import MultiSubmitter, ProcessorSubmitter
from app.core.tables import DisputeRow, EvidenceRow
from app.settings import settings

MAX_NOTE_CHARS = 2000
SUBMISSION_ID = re.compile(r"^sub_[0-9a-f]{12}$")
PAYPAL_ORDER_ID = re.compile(r"^[A-Z0-9]{1,36}$")

router = APIRouter()
router.include_router(insights_router)


def get_charge_lookup() -> stripe_ingest.ChargeLookup:
    return stripe_ingest.fetch_charge_info


def get_collector() -> EvidenceCollector:
    return stripe_ingest.default_collector()


def get_submitter() -> ProcessorSubmitter:
    return MultiSubmitter()


def get_paypal_client() -> PayPalClient:
    return PayPalClient()


def _require_paypal_sandbox(client: PayPalClient) -> None:
    available, reason = client.available()
    if not available:
        raise ApiError(503, "paypal_unavailable", reason)


def _paypal_checkout_error(exc: PayPalError) -> ApiError:
    status = exc.status if exc.status and 400 <= exc.status <= 599 else 502
    return ApiError(status, "paypal_checkout_failed", exc.message)


def get_paypal_dispute_lookup() -> paypal_ingest.DisputeLookup:
    return paypal_ingest.fetch_dispute


def get_paypal_collector(
    client: PayPalClient = Depends(get_paypal_client),
) -> EvidenceCollector:
    # PayPal's own record first, then the shop's order/shipping/policy facts.
    return PayPalCollector(client, shop=stripe_ingest.default_collector())


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    background: BackgroundTasks,
    stripe_signature: str | None = Header(default=None),
    charge_lookup: stripe_ingest.ChargeLookup = Depends(get_charge_lookup),
    collector: EvidenceCollector = Depends(get_collector),
) -> dict[str, str]:
    payload = await request.body()  # raw bytes: signature is computed over them
    try:
        event = stripe_ingest.verify_and_parse(payload, stripe_signature)
    except stripe_ingest.WebhookNotConfigured as exc:
        raise ApiError(503, "webhook_not_configured", str(exc)) from exc
    except stripe_ingest.SignatureError as exc:
        raise ApiError(400, "invalid_signature", "Stripe signature verification failed") from exc

    def apply() -> str:
        with session_factory()() as session:
            return stripe_ingest.handle_event(session, event, charge_lookup, collector)

    outcome = await run_in_threadpool(apply)
    if event["type"] == "charge.dispute.closed" and outcome in ("created", "updated"):
        # After the response: teach the agent the real result (best effort, idempotent).
        background.add_task(outcome_report.report_closed, event["data"]["object"]["id"])
    return {"received": event["id"], "outcome": outcome}


@router.post("/webhooks/paypal")
async def paypal_webhook(
    request: Request,
    background: BackgroundTasks,
    client: PayPalClient = Depends(get_paypal_client),
    dispute_lookup: paypal_ingest.DisputeLookup = Depends(get_paypal_dispute_lookup),
    collector: EvidenceCollector = Depends(get_paypal_collector),
) -> dict[str, str]:
    payload = await request.body()  # raw bytes: PayPal verifies the signature over them
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        event = await run_in_threadpool(paypal_ingest.verify_and_parse, payload, headers, client)
    except paypal_ingest.WebhookNotConfigured as exc:
        raise ApiError(503, "webhook_not_configured", str(exc)) from exc
    except paypal_ingest.SignatureError as exc:
        raise ApiError(400, "invalid_signature", "PayPal signature verification failed") from exc

    def apply() -> str:
        with session_factory()() as session:
            return paypal_ingest.handle_event(session, event, dispute_lookup, collector)

    outcome = await run_in_threadpool(apply)
    if event.get("event_type") == "CUSTOMER.DISPUTE.RESOLVED" and outcome in ("created", "updated"):
        background.add_task(outcome_report.report_closed, event["resource"]["dispute_id"])
    return {"received": event["id"], "outcome": outcome}


@router.post("/paypal/checkout/orders")
async def create_paypal_checkout_order(
    client: PayPalClient = Depends(get_paypal_client),
) -> dict:
    """Create a fixed USD $10 Sandbox purchase; amount is never accepted from the browser."""
    _require_paypal_sandbox(client)
    try:
        return await run_in_threadpool(client.create_checkout_order)
    except PayPalError as exc:
        raise _paypal_checkout_error(exc) from exc


@router.post("/paypal/checkout/orders/{order_id}/capture")
async def capture_paypal_checkout_order(
    order_id: str,
    client: PayPalClient = Depends(get_paypal_client),
) -> dict:
    """Capture a PayPal-approved Sandbox order."""
    if not PAYPAL_ORDER_ID.fullmatch(order_id):
        raise ApiError(422, "invalid_order_id", "PayPal order ID has an invalid format")
    _require_paypal_sandbox(client)
    try:
        return await run_in_threadpool(client.capture_checkout_order, order_id)
    except PayPalError as exc:
        raise _paypal_checkout_error(exc) from exc


@router.get("/disputes", response_model=list[Dispute])
def disputes(
    status: DisputeStatus | None = None, session: Session = Depends(get_session)
) -> list[Dispute]:
    return list_disputes(session, status=status)


@router.get("/disputes/{dispute_id}", response_model=DisputeDetail)
def dispute_detail(dispute_id: str, session: Session = Depends(get_session)) -> DisputeDetail:
    detail = get_dispute(session, dispute_id)
    if detail is None:
        raise ApiError(404, "not_found", f"dispute {dispute_id} not found")
    return detail


@router.post("/disputes/{dispute_id}/collect", response_model=DisputeDetail)
def collect_evidence(
    dispute_id: str,
    session: Session = Depends(get_session),
    collector: EvidenceCollector = Depends(get_collector),
    paypal_collector: EvidenceCollector = Depends(get_paypal_collector),
) -> DisputeDetail:
    """Re-run evidence collection. Idempotent: evidence ids derive from the source records."""
    row = session.get(DisputeRow, dispute_id)
    if row is None:
        raise ApiError(404, "not_found", f"dispute {dispute_id} not found")
    collect_for_dispute(session, row, paypal_collector if row.processor == "paypal" else collector)
    session.commit()
    detail = get_dispute(session, dispute_id)
    assert detail is not None
    return detail


@router.post("/disputes/{dispute_id}/evidence", response_model=list[EvidenceItem], status_code=201)
async def add_evidence(
    dispute_id: str,
    note: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
) -> list[EvidenceItem]:
    """Seller note and/or file upload. Everything the seller supplies is stored verified=false:
    it is shown to the seller and may be attached, but can never back a claim."""
    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE_CHARS:
        raise ApiError(422, "note_too_long", f"note exceeds {MAX_NOTE_CHARS} characters")
    if not note and file is None:
        raise ApiError(422, "nothing_to_add", "provide a note, a file, or both")

    stored_name = shown_name = None
    if file is not None:
        try:
            data = await uploads.read_limited(file)
            ext = uploads.sniff_extension(data)
        except uploads.UploadError as exc:
            raise ApiError(exc.status_code, exc.error, exc.detail) from exc
        shown_name = uploads.display_name(file.filename)
        stored_name = await run_in_threadpool(uploads.store, data, ext)

    def save() -> list[EvidenceItem]:
        now = datetime.now(UTC)
        with session_factory()() as session:
            if session.get(DisputeRow, dispute_id) is None:
                raise ApiError(404, "not_found", f"dispute {dispute_id} not found")
            rows: list[EvidenceRow] = []
            if note:
                rows.append(
                    EvidenceRow(
                        id="ev_" + secrets.token_hex(6),
                        dispute_id=dispute_id,
                        type="seller_note",
                        source="seller_claim",
                        verified=False,
                        summary=note,
                        uri=None,
                        captured_at=now,
                    )
                )
            if stored_name:
                rows.append(
                    EvidenceRow(
                        id="ev_" + secrets.token_hex(6),
                        dispute_id=dispute_id,
                        type="seller_upload",
                        source="seller_upload",
                        verified=False,
                        summary=f"Seller upload: {shown_name}",
                        uri=f"files/{stored_name}",
                        captured_at=now,
                    )
                )
            session.add_all(rows)
            session.commit()
            return [to_evidence(r) for r in rows]

    try:
        return await run_in_threadpool(save)
    except ApiError:
        if stored_name and (path := uploads.path_for(stored_name)):
            path.unlink(missing_ok=True)  # no orphan file for an unknown dispute
        raise


@router.get("/files/{name}")
def get_file(name: str) -> FileResponse:
    path = uploads.path_for(name)
    if path is None:
        raise ApiError(404, "not_found", "file not found")
    ext = name.rsplit(".", 1)[1]
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, max-age=3600",
    }
    if ext == "pdf":  # never render PDFs inline on the API origin
        headers["Content-Disposition"] = f'attachment; filename="evidence-{name[:8]}.pdf"'
    return FileResponse(path, media_type=uploads.CONTENT_TYPES[ext], headers=headers)


# -- Phase 4: review, approval, submission, acceptance --------------------------------------
@router.post("/disputes/{dispute_id}/letter-preview", response_model=LetterPreview)
def letter_preview(
    dispute_id: str, body: LetterRequest, session: Session = Depends(get_session)
) -> LetterPreview:
    """Render exactly what approval would send, report unsourced claims, and return the hash that
    approval must echo back."""
    return submissions.preview(session, dispute_id, body)


@router.put("/disputes/{dispute_id}/draft")
def save_draft(
    dispute_id: str,
    body: LetterRequest,
    memory_mode: Literal["on", "off"] = "on",
    session: Session = Depends(get_session),
) -> dict[str, str]:
    status = submissions.save_draft(session, dispute_id, body, memory_mode)
    return {"status": status}


@router.get("/disputes/{dispute_id}/draft")
def get_saved_draft(dispute_id: str, session: Session = Depends(get_session)) -> dict:
    draft = submissions.saved_draft(session, dispute_id)
    if draft is None:
        raise ApiError(404, "not_found", "no saved draft for this dispute")
    return draft


@router.post("/disputes/{dispute_id}/approve", response_model=Submission)
def approve(
    dispute_id: str,
    body: ApproveRequest,
    session: Session = Depends(get_session),
    submitter: ProcessorSubmitter = Depends(get_submitter),
) -> Submission:
    """The seller's explicit approval. Builds the PDF packet and, if possible, submits it."""
    return submissions.approve(session, dispute_id, body, submitter)


@router.post("/disputes/{dispute_id}/accept", response_model=AcceptResult)
def accept(
    dispute_id: str,
    body: AcceptRequest,
    session: Session = Depends(get_session),
    submitter: ProcessorSubmitter = Depends(get_submitter),
) -> AcceptResult:
    return submissions.accept(session, dispute_id, body, submitter)


@router.get("/processor-status")
def processor_status(
    processor: Literal["stripe", "paypal"] = "stripe",
    submitter: ProcessorSubmitter = Depends(get_submitter),
) -> dict:
    """Whether approving a response would really be sent, so the UI can say so honestly."""
    active = submissions.resolve_submitter(submitter, processor)
    available, why = active.available() if active else (False, f"{processor} is not supported")
    return {"can_submit": available, "reason": why or None, "demo_tools": settings.demo_tools}


@router.get("/disputes/{dispute_id}/submission", response_model=Submission)
def latest_submission(dispute_id: str, session: Session = Depends(get_session)) -> Submission:
    sub = submissions.latest_submission(session, dispute_id)
    if sub is None:
        raise ApiError(404, "not_found", "no response has been approved for this dispute")
    return sub


@router.get("/submissions/{submission_id}/pdf")
def submission_pdf(submission_id: str) -> FileResponse:
    path = settings.upload_dir / "packets" / f"{submission_id}.pdf"
    if not SUBMISSION_ID.fullmatch(submission_id) or not path.is_file():
        raise ApiError(404, "not_found", "packet not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="response-{submission_id}.pdf"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


class SimulateOutcomeRequest(BaseModel):
    outcome: Literal["won", "lost"]


@router.post("/disputes/{dispute_id}/simulate-outcome")
def simulate_outcome(
    dispute_id: str, body: SimulateOutcomeRequest, session: Session = Depends(get_session)
) -> dict[str, str]:
    """DEMO ONLY (needs DEMO_TOOLS=1): stand in for the bank's decision on a responded dispute."""
    return {"status": demo.simulate_outcome(session, dispute_id, body.outcome), "simulated": "true"}


@router.post("/alerts/run", response_model=list[Alert])
def run_alerts_now(session: Session = Depends(get_session)) -> list[Alert]:
    """Send the 72h/24h/6h warnings that are due for disputes waiting on the seller."""
    return [Alert.model_validate(a, from_attributes=True) for a in alerts.run_alerts(session)]


@router.get("/alerts", response_model=list[Alert])
def list_sent_alerts(session: Session = Depends(get_session)) -> list[Alert]:
    return [Alert.model_validate(a, from_attributes=True) for a in alerts.list_alerts(session)]
