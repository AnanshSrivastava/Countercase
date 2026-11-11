# ruff: noqa: E501
"""PayPal adapter: mapping, client wire format, webhook ingestion, and the approve -> send path.

No network: PayPal is replaced by httpx.MockTransport, which records every request.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.paypal import ingest, mapping
from app.core.paypal.client import PayPalClient, PayPalError
from app.core.paypal.submitter import PayPalSubmitter
from app.core.processors import MultiSubmitter, SubmitError
from app.core.router import get_paypal_client, get_submitter
from app.core.tables import DisputeRow, EvidenceRow
from app.main import app
from app.settings import settings

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "paypal"
CREATED = json.loads((FIXTURES / "dispute_created_not_received.json").read_text())
RESOLVED = json.loads((FIXTURES / "dispute_resolved_seller_favour.json").read_text())


class Recorder:
    """MockTransport handler: answers PayPal's token/evidence/verify endpoints, records the rest."""

    def __init__(self, evidence_status=200, verified="SUCCESS", dispute=None) -> None:
        self.requests: list[httpx.Request] = []
        self.evidence_status, self.verified, self.dispute = evidence_status, verified, dispute or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if path.endswith("/provide-evidence"):
            if self.evidence_status != 200:
                return httpx.Response(
                    self.evidence_status,
                    json={
                        "name": "UNPROCESSABLE_ENTITY",
                        "details": [{"issue": "MISSING_TRACKING"}],
                    },
                )
            return httpx.Response(200, json={"links": []})
        if path.endswith("/accept-claim"):
            return httpx.Response(200, json={})
        if path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": self.verified})
        if path.startswith("/v1/customer/disputes/"):
            return httpx.Response(200, json=self.dispute)
        return httpx.Response(404, json={"name": "NOT_FOUND"})

    def client(self) -> PayPalClient:
        return PayPalClient(
            "id", "secret", "https://api-m.sandbox.paypal.com", httpx.MockTransport(self)
        )


# -- pure mapping --------------------------------------------------------------------------------
def test_money_is_converted_to_minor_units() -> None:
    assert mapping.to_minor("129.00", "USD") == 12900
    assert mapping.to_minor("0.10", "usd") == 10
    assert mapping.to_minor("500", "JPY") == 500  # zero-decimal currency


@pytest.mark.parametrize(
    ("status", "outcome", "expected"),
    [
        ("WAITING_FOR_SELLER_RESPONSE", None, "needs_response"),
        ("UNDER_REVIEW", None, "submitted"),
        ("RESOLVED", "RESOLVED_SELLER_FAVOUR", "won"),
        ("RESOLVED", "RESOLVED_BUYER_FAVOUR", "lost"),
        ("RESOLVED", "DENIED", None),  # ambiguous: never counted as a win or a loss
        ("SOMETHING_NEW", None, None),
    ],
)
def test_status_mapping(status, outcome, expected) -> None:
    assert mapping.map_dispute_status(status, outcome) == expected


def test_evidence_uses_typed_fulfilment_proof_when_tracking_is_known() -> None:
    ev = mapping.build_evidences(
        "not_received",
        letter_text="letter",
        pdf_name="r.pdf",
        courier="FedEx",
        tracking_number="122533485",
    )
    assert [e["evidence_type"] for e in ev] == ["PROOF_OF_FULFILLMENT", "OTHER"]
    assert ev[0]["evidence_info"]["tracking_info"] == [
        {"carrier_name": "FEDEX", "tracking_number": "122533485"}
    ]
    assert ev[1]["documents"] == [{"name": "r.pdf"}]


def test_unknown_carrier_goes_out_as_other_and_no_tracking_means_only_other() -> None:
    ev = mapping.build_evidences(
        "not_received", letter_text="x", pdf_name="r.pdf", courier="CourierX", tracking_number="T1"
    )
    assert ev[0]["evidence_info"]["tracking_info"][0] == {
        "carrier_name": "OTHER",
        "carrier_name_other": "CourierX",
        "tracking_number": "T1",
    }
    only = mapping.build_evidences(
        "unauthorized", letter_text="x", pdf_name="r.pdf", courier="FedEx", tracking_number="T1"
    )
    assert [e["evidence_type"] for e in only] == ["OTHER"]  # tracking proves nothing here


def test_long_letters_are_truncated_for_notes_but_pointed_at_the_pdf() -> None:
    ev = mapping.build_evidences(
        "other", letter_text="a" * 5000, pdf_name="r.pdf", courier=None, tracking_number=None
    )
    assert len(ev[0]["notes"]) <= mapping.NOTES_LIMIT
    assert ev[0]["notes"].endswith("(full response in the attached PDF)")


# -- client wire format --------------------------------------------------------------------------
def test_client_refuses_anything_that_is_not_the_sandbox() -> None:
    live = PayPalClient("id", "secret", "https://api-m.paypal.com")
    assert live.available()[0] is False
    assert PayPalClient("", "", "https://api-m.sandbox.paypal.com").available()[0] is False
    assert Recorder().client().available() == (True, "")


def test_provide_evidence_is_multipart_with_input_part_document_and_idempotency_key() -> None:
    rec = Recorder()
    rec.client().provide_evidence(
        "PP-D-1", [{"evidence_type": "OTHER"}], {"r.pdf": b"%PDF"}, "sub_1"
    )
    req = rec.requests[-1]
    assert req.url.path == "/v1/customer/disputes/PP-D-1/provide-evidence"
    assert req.headers["PayPal-Request-Id"] == "sub_1"
    assert req.headers["Authorization"] == "Bearer tok"
    body = req.read()
    assert b'name="input"' in body and b'filename="r.pdf"' in body
    assert b'"evidences"' in body


def test_verify_webhook_forwards_the_raw_body_unchanged() -> None:
    rec = Recorder()
    raw = b'{"id":"WH-1",   "weird":  "spacing"}'
    headers = {
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-cert-url": "https://api.sandbox.paypal.com/cert",
        "paypal-transmission-id": "t1",
        "paypal-transmission-sig": "sig",
        "paypal-transmission-time": "2026-11-09T08:30:05Z",
    }
    assert rec.client().verify_webhook(headers, raw) is True
    sent = rec.requests[-1].read().decode()
    assert raw.decode() in sent  # byte-for-byte, so PayPal's signature check can pass
    assert json.loads(sent)["webhook_event"]["id"] == "WH-1"
    assert rec.client().verify_webhook({}, raw) is False  # missing headers: never "verified"


def test_paypal_errors_carry_the_issue_code() -> None:
    with pytest.raises(PayPalError) as err:
        Recorder(evidence_status=422).client().provide_evidence("PP-D-1", [], {}, "k")
    assert err.value.code == "MISSING_TRACKING"


# -- submitter -----------------------------------------------------------------------------------
def test_submitter_sends_typed_evidence_and_maps_errors() -> None:
    rec = Recorder()
    PayPalSubmitter(rec.client()).submit(
        processor_dispute_id="PP-D-1",
        idempotency_key="sub_9",
        letter_text="L",
        packet_pdf=b"%PDF",
        shipping_carrier="UPS",
        tracking_number="1Z999",
        category="not_received",
    )
    sent = rec.requests[-1].read().decode()
    assert "PROOF_OF_FULFILLMENT" in sent and "1Z999" in sent and "response-sub_9.pdf" in sent

    failing = PayPalSubmitter(Recorder(evidence_status=422).client())
    with pytest.raises(SubmitError) as err:
        failing.submit(
            processor_dispute_id="PP-D-1",
            idempotency_key="sub_9",
            letter_text="L",
            packet_pdf=b"x",
            shipping_carrier=None,
        )
    assert err.value.code == "MISSING_TRACKING"


def test_is_submitted_looks_for_seller_evidence() -> None:
    no = Recorder(dispute={"evidences": [{"source": "REQUESTED_FROM_SELLER"}]})
    yes = Recorder(dispute={"evidences": [{"source": "SUBMITTED_BY_SELLER"}]})
    assert PayPalSubmitter(no.client()).is_submitted("PP-D-1") is False
    assert PayPalSubmitter(yes.client()).is_submitted("PP-D-1") is True


# -- webhook ingestion (needs Postgres, like the Stripe tests) -------------------------------------
@pytest.fixture
def paypal(session, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(settings, "paypal_webhook_id", "WEBHOOK-ID")
    app.dependency_overrides[get_paypal_client] = lambda: rec.client()
    yield SimpleNamespaceLike(rec=rec, client=TestClient(app), session=session)
    app.dependency_overrides.clear()


class SimpleNamespaceLike:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)


SIG_HEADERS = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/cert",
    "PAYPAL-TRANSMISSION-ID": "t1",
    "PAYPAL-TRANSMISSION-SIG": "sig",
    "PAYPAL-TRANSMISSION-TIME": "2026-11-09T08:30:05Z",
}


def post(p, payload):
    return p.client.post(
        "/core/webhooks/paypal",
        content=json.dumps(payload),
        headers={**SIG_HEADERS, "Content-Type": "application/json"},
    )


def only_dispute(p) -> DisputeRow:
    p.session.expire_all()
    return p.session.query(DisputeRow).one()


def test_created_event_makes_a_classified_dispute_with_shop_evidence(paypal) -> None:
    resp = post(paypal, CREATED)
    assert resp.status_code == 200 and resp.json()["outcome"] == "created"
    d = only_dispute(paypal)
    assert (d.processor, d.processor_dispute_id) == ("paypal", "PP-D-27803")
    assert (d.amount, d.currency, d.category, d.status) == (
        12900,
        "usd",
        "not_received",
        "needs_response",
    )
    assert d.deadline_at == datetime(2026, 11, 20, 8, 30, tzinfo=UTC)
    assert d.processor_charge_id == "5O190127TN364715T"
    assert d.processor_meta["life_cycle_stage"] == "CHARGEBACK"
    # Order matched via invoice_number -> the mock shop supplied verified evidence and tracking.
    assert d.order_id == "ord_102" and d.tracking_number
    types = {e.type for e in paypal.session.query(EvidenceRow).filter_by(dispute_id=d.id)}
    assert {"order_receipt", "tracking"} <= types


def test_no_raw_buyer_identity_is_stored(paypal) -> None:
    post(paypal, CREATED)
    d = only_dispute(paypal)
    stored = json.dumps([d.customer_hash, d.processor_meta])
    assert "alex@example.com" not in stored and d.customer_hash.startswith("c_")


def test_duplicate_stale_and_resolved_events(paypal) -> None:
    assert post(paypal, CREATED).json()["outcome"] == "created"
    assert post(paypal, CREATED).json()["outcome"] == "duplicate"
    assert post(paypal, RESOLVED).json()["outcome"] == "updated"
    assert only_dispute(paypal).status == "won"
    late = {**CREATED, "id": "WH-LATE", "event_type": "CUSTOMER.DISPUTE.UPDATED"}
    assert post(paypal, late).json()["outcome"] == "stale"  # older than the resolution
    assert only_dispute(paypal).status == "won"


def test_unverified_signature_is_rejected_and_nothing_is_stored(paypal) -> None:
    paypal.rec.verified = "FAILURE"
    resp = post(paypal, CREATED)
    assert resp.status_code == 400 and resp.json()["error"] == "invalid_signature"
    assert paypal.session.query(DisputeRow).count() == 0


def test_webhook_needs_a_webhook_id_and_verification_is_demo_only(paypal, monkeypatch) -> None:
    monkeypatch.setattr(settings, "paypal_webhook_id", "")
    assert post(paypal, CREATED).status_code == 503
    monkeypatch.setattr(settings, "paypal_webhook_id", "WEBHOOK-ID")
    monkeypatch.setattr(settings, "paypal_verify_webhooks", False)
    monkeypatch.setattr(settings, "demo_tools", False)
    assert post(paypal, CREATED).status_code == 503  # cannot skip verification outside the demo
    monkeypatch.setattr(settings, "demo_tools", True)
    assert post(paypal, CREATED).status_code == 200


def test_unknown_event_types_are_ignored(paypal) -> None:
    other = {**CREATED, "id": "WH-X", "event_type": "PAYMENT.CAPTURE.COMPLETED"}
    assert post(paypal, other).json()["outcome"] == "ignored"


# -- approve -> PayPal ---------------------------------------------------------------------------
def test_approve_sends_the_packet_to_paypal_and_marks_submitted(
    paypal, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    multi = MultiSubmitter()
    multi._paypal = PayPalSubmitter(paypal.rec.client())
    app.dependency_overrides[get_submitter] = lambda: multi

    post(paypal, CREATED)
    d = only_dispute(paypal)
    ev = {
        e.type: e.id
        for e in paypal.session.query(EvidenceRow).filter_by(dispute_id=d.id, verified=True)
    }
    claims = [
        {"text": "The order was placed and paid in full.", "evidence_id": ev["order_receipt"]},
        {"text": "The parcel shipped with tracking.", "evidence_id": ev["tracking"]},
    ]
    req = {"claims": claims, "seller_statement": None, "attach_upload_ids": []}
    preview = paypal.client.post(f"/core/disputes/{d.id}/letter-preview", json=req).json()
    resp = paypal.client.post(
        f"/core/disputes/{d.id}/approve",
        json={**req, "approved": True, "letter_sha256": preview["letter_sha256"]},
    )
    assert resp.status_code == 200 and resp.json()["status"] == "submitted"

    sent = [r for r in paypal.rec.requests if r.url.path.endswith("/provide-evidence")]
    assert (
        len(sent) == 1 and sent[0].url.path == "/v1/customer/disputes/PP-D-27803/provide-evidence"
    )
    body = sent[0].read().decode("latin-1")
    assert "PROOF_OF_FULFILLMENT" in body and "%PDF" in body
    assert only_dispute(paypal).status == "submitted"


def test_paypal_disputes_are_exported_not_sent_when_credentials_are_missing(
    paypal, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    multi = MultiSubmitter()
    multi._paypal = PayPalSubmitter(PayPalClient("", "", "https://api-m.sandbox.paypal.com"))
    app.dependency_overrides[get_submitter] = lambda: multi
    post(paypal, CREATED)
    d = only_dispute(paypal)
    ev_id = (
        paypal.session.query(EvidenceRow).filter_by(dispute_id=d.id, type="order_receipt").one().id
    )
    req = {"claims": [{"text": "Paid in full.", "evidence_id": ev_id}], "attach_upload_ids": []}
    sha = paypal.client.post(f"/core/disputes/{d.id}/letter-preview", json=req).json()[
        "letter_sha256"
    ]
    resp = paypal.client.post(
        f"/core/disputes/{d.id}/approve", json={**req, "approved": True, "letter_sha256": sha}
    )
    assert (
        resp.json()["status"] == "exported"
        and "no PayPal sandbox credentials" in resp.json()["note"]
    )


def test_ingest_module_exposes_the_documented_event_set() -> None:
    assert ingest.HANDLED_EVENTS == {
        "CUSTOMER.DISPUTE.CREATED",
        "CUSTOMER.DISPUTE.UPDATED",
        "CUSTOMER.DISPUTE.RESOLVED",
    }
