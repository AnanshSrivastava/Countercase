"""Pure PayPal <-> Countercase mapping. No I/O, so it is cheap to test and easy to audit.

Where PayPal's vocabulary has no clean Countercase equivalent the value is left unmapped (status kept)
rather than guessed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.core.money import ZERO_DECIMAL

# PayPal dispute `status` -> Countercase status. Anything not listed keeps the current status.
PAYPAL_STATUS = {
    "OPEN": "needs_response",
    "WAITING_FOR_SELLER_RESPONSE": "needs_response",
    "WAITING_FOR_BUYER_RESPONSE": "submitted",
    "UNDER_REVIEW": "submitted",
}

# RESOLVED is decided by dispute_outcome.outcome_code. DENIED is deliberately absent: it is not
# clear from the docs whose claim was denied, so it must not be counted as a win or a loss.
PAYPAL_OUTCOME = {
    "RESOLVED_SELLER_FAVOUR": "won",
    "CANCELED_BY_BUYER": "won",
    "RESOLVED_BUYER_FAVOUR": "lost",
    "RESOLVED_WITH_PAYOUT": "lost",
    "ACCEPTED": "accepted",
}


def map_dispute_status(paypal_status: str | None, outcome_code: str | None) -> str | None:
    if paypal_status == "RESOLVED":
        return PAYPAL_OUTCOME.get(outcome_code or "")
    return PAYPAL_STATUS.get(paypal_status or "")


def to_minor(value: str, currency: str) -> int:
    """PayPal sends decimal strings ('129.00'); Countercase stores minor units."""
    exp = 0 if currency.lower() in ZERO_DECIMAL else 2
    return int((Decimal(value) * (10**exp)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


# PayPal carrier enum values we can state with confidence; anything else goes out as OTHER.
KNOWN_CARRIERS = {
    "fedex": "FEDEX",
    "ups": "UPS",
    "usps": "USPS",
    "dhl": "DHL",
    "dhl express": "DHL",
    "royal mail": "ROYAL_MAIL",
}
NOTES_LIMIT = 2000  # PayPal notes are capped; the full letter always travels in the PDF


def carrier_fields(courier: str) -> dict:
    code = KNOWN_CARRIERS.get(courier.strip().lower())
    if code:
        return {"carrier_name": code}
    return {"carrier_name": "OTHER", "carrier_name_other": courier.strip()[:64]}


def build_evidences(
    category: str | None,
    *,
    letter_text: str,
    pdf_name: str,
    courier: str | None,
    tracking_number: str | None,
) -> list[dict]:
    """Our approved response -> PayPal `evidences[]`.

    PayPal wants typed evidence (PROOF_OF_FULFILLMENT carries carrier + tracking number;
    PROOF_OF_REFUND carries refund ids; OTHER carries notes and documents). We only ever send what
    we hold as verified facts: tracking when the shop collector gave us one, and the packet PDF.
    Refund ids are not collected yet, so refund-type disputes go out as OTHER.
    """
    evidences: list[dict] = []
    if category == "not_received" and courier and tracking_number:
        evidences.append(
            {
                "evidence_type": "PROOF_OF_FULFILLMENT",
                "evidence_info": {
                    "tracking_info": [
                        {**carrier_fields(courier), "tracking_number": tracking_number}
                    ]
                },
                "notes": "Shipment tracking from the seller's order system.",
            }
        )
    notes = letter_text
    if len(notes) > NOTES_LIMIT:
        suffix = "... (full response in the attached PDF)"
        notes = notes[: NOTES_LIMIT - len(suffix)] + suffix
    evidences.append({"evidence_type": "OTHER", "notes": notes, "documents": [{"name": pdf_name}]})
    return evidences
