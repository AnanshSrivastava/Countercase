"""PayPalSubmitter: sends an approved response through the Disputes API (sandbox only).

Mirrors StripeSubmitter's contract. `submit` is final from the seller's side, so: the submission id
is the idempotency key (PayPal-Request-Id), and `is_submitted` lets the core reconcile a `pending`
attempt after a crash instead of sending twice.
"""

from __future__ import annotations

import logging

from app.core.paypal import mapping
from app.core.paypal.client import PayPalClient, PayPalError
from app.core.processors import SubmitError

log = logging.getLogger(__name__)


class PayPalSubmitter:
    def __init__(self, client: PayPalClient | None = None) -> None:
        self.client = client or PayPalClient()

    def available(self) -> tuple[bool, str]:
        return self.client.available()

    def is_submitted(self, processor_dispute_id: str) -> bool:
        try:
            dispute = self.client.get_dispute(processor_dispute_id)
        except PayPalError as exc:
            raise SubmitError(exc.code, exc.message) from exc
        return any(e.get("source") == "SUBMITTED_BY_SELLER" for e in dispute.get("evidences") or [])

    def submit(
        self,
        *,
        processor_dispute_id: str,
        idempotency_key: str,
        letter_text: str,
        packet_pdf: bytes,
        shipping_carrier: str | None,
        tracking_number: str | None = None,
        category: str | None = None,
    ) -> None:
        pdf_name = f"response-{idempotency_key}.pdf"
        evidences = mapping.build_evidences(
            category,
            letter_text=letter_text,
            pdf_name=pdf_name,
            courier=shipping_carrier,
            tracking_number=tracking_number,
        )
        try:
            self.client.provide_evidence(
                processor_dispute_id, evidences, {pdf_name: packet_pdf}, idempotency_key
            )
        except PayPalError as exc:
            log.warning("paypal submit failed for %s: %s", processor_dispute_id, exc.code)
            raise SubmitError(exc.code, exc.message) from exc

    def close(self, processor_dispute_id: str) -> None:
        try:
            self.client.accept_claim(
                processor_dispute_id,
                "Seller accepted the claim after review.",
                f"accept-{processor_dispute_id}",
            )
        except PayPalError as exc:
            raise SubmitError(exc.code, exc.message) from exc
