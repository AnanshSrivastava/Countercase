"""Processor adapter for submitting a response (F5) or accepting a dispute.

`submit=true` is final: the bank sees the evidence and it cannot be changed. So this module is
defensive by construction:
- Only Stripe TEST keys are ever used. A live key makes the adapter report itself unavailable and
  the response is exported as a PDF instead.
- Each attempt uploads a fresh file (a Stripe file id can be used once) and passes the submission id
  as the idempotency key, so a network retry can never submit twice.
- Errors are mapped by `error.code`, never by parsing messages.
"""

import io
import logging
from typing import Protocol

import stripe

from app.settings import settings

log = logging.getLogger(__name__)

PAGE_LIMIT_CODE = "dispute_evidence_page_limit_exceeded"


class SubmitError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class ProcessorSubmitter(Protocol):
    def available(self) -> tuple[bool, str]:
        """(True, "") when a real submission is possible, else (False, why not)."""

    def is_submitted(self, processor_dispute_id: str) -> bool: ...

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
    ) -> None: ...

    def close(self, processor_dispute_id: str) -> None:
        """Accept the dispute (concede it) at the processor."""


class StripeSubmitter:
    def __init__(self, secret_key: str | None = None) -> None:
        self.key = settings.stripe_secret_key if secret_key is None else secret_key

    def available(self) -> tuple[bool, str]:
        key = self.key
        if not key or key.endswith("xxx"):
            return False, "no Stripe test key is configured"
        if not key.startswith(("sk_test_", "rk_test_")):
            return False, "only Stripe test-mode keys are used; this key is not a test key"
        return True, ""

    def _client(self) -> stripe.StripeClient:
        return stripe.StripeClient(self.key, max_network_retries=2)

    def is_submitted(self, processor_dispute_id: str) -> bool:
        try:
            dispute = self._client().v1.disputes.retrieve(processor_dispute_id)
        except stripe.StripeError as exc:
            raise SubmitError(getattr(exc, "code", None) or "stripe_error", str(exc)) from exc
        details = dispute.to_dict().get("evidence_details") or {}
        return bool(details.get("submission_count"))

    def submit(
        self,
        *,
        processor_dispute_id: str,
        idempotency_key: str,
        letter_text: str,
        packet_pdf: bytes,
        shipping_carrier: str | None,
        tracking_number: str | None = None,  # PayPal-only inputs; Stripe ignores them
        category: str | None = None,
    ) -> None:
        client = self._client()
        try:
            uploaded = client.v1.files.create(
                {"purpose": "dispute_evidence", "file": io.BytesIO(packet_pdf)},
                {"idempotency_key": f"{idempotency_key}:file"},
            )
            evidence = {"uncategorized_file": uploaded.id, "uncategorized_text": letter_text}
            if shipping_carrier:
                evidence["shipping_carrier"] = shipping_carrier
            client.v1.disputes.update(
                processor_dispute_id,
                {"evidence": evidence, "submit": True},
                {"idempotency_key": idempotency_key},
            )
        except stripe.StripeError as exc:
            code = getattr(exc, "code", None) or "stripe_error"
            log.warning("stripe submit failed for %s: %s", processor_dispute_id, code)
            if code == PAGE_LIMIT_CODE:
                raise SubmitError(
                    code,
                    "The packet has more pages than this card network allows "
                    "(Mastercard allows 19). Remove an attachment and try again.",
                ) from exc
            raise SubmitError(code, str(exc)) from exc

    def close(self, processor_dispute_id: str) -> None:
        try:
            self._client().v1.disputes.close(processor_dispute_id)
        except stripe.StripeError as exc:
            raise SubmitError(getattr(exc, "code", None) or "stripe_error", str(exc)) from exc


class MultiSubmitter:
    """One entry point for every processor. `for_processor` returns None for unsupported ones."""

    def __init__(self) -> None:
        self._stripe = StripeSubmitter()
        self._paypal = None

    def for_processor(self, processor: str) -> ProcessorSubmitter | None:
        if processor == "stripe":
            return self._stripe
        if processor == "paypal":
            if self._paypal is None:  # imported lazily: paypal.submitter imports this module
                from app.core.paypal.submitter import PayPalSubmitter

                self._paypal = PayPalSubmitter()
            return self._paypal
        return None
