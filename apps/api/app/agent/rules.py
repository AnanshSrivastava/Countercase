# ruff: noqa: E501
"""Static rules: processor reason code -> category, and evidence checklists per category.

Pure data, no I/O. Checklist wording for card-network rules (e.g. Visa CE 3.0) must be
verified against current network/Stripe docs before being quoted to users.
"""

CATEGORIES = (
    "not_received",
    "unauthorized",
    "not_as_described",
    "duplicate",
    "subscription_cancelled",
    "refund_not_processed",
    "other",
)

# Stripe dispute reason -> (category, plain-language explanation)
STRIPE_REASONS: dict[str, tuple[str, str]] = {
    "product_not_received": ("not_received", "The customer says the item never arrived."),
    "fraudulent": ("unauthorized", "The cardholder says they did not make this purchase."),
    "unrecognized": ("unauthorized", "The cardholder does not recognise this charge."),
    "product_unacceptable": (
        "not_as_described",
        "The customer says the item was not as described or was faulty.",
    ),
    "duplicate": (
        "duplicate",
        "The customer says they were charged more than once for the same thing.",
    ),
    "subscription_canceled": (
        "subscription_cancelled",
        "The customer says they cancelled but were still charged.",
    ),
    "credit_not_processed": (
        "refund_not_processed",
        "The customer says an expected refund never arrived.",
    ),
}

# PayPal dispute `reason` -> (category, plain-language explanation).
# Source: developer.paypal.com/disputes/reasons-evidence. Both spellings of UNAUTHORI[SZ]ED are
# accepted because PayPal's docs and payloads have used each.
PAYPAL_REASONS: dict[str, tuple[str, str]] = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": (
        "not_received",
        "The buyer says the item or service never arrived.",
    ),
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": (
        "not_as_described",
        "The buyer says the item or service was not as described.",
    ),
    "UNAUTHORISED": ("unauthorized", "The buyer says they did not authorise this purchase."),
    "UNAUTHORIZED": ("unauthorized", "The buyer says they did not authorise this purchase."),
    "CREDIT_NOT_PROCESSED": (
        "refund_not_processed",
        "The buyer says an expected refund or credit never arrived.",
    ),
    "DUPLICATE_TRANSACTION": (
        "duplicate",
        "The buyer says they were charged more than once for the same thing.",
    ),
    "CANCELED_RECURRING_BILLING": (
        "subscription_cancelled",
        "The buyer says they cancelled but were still billed.",
    ),
    "INCORRECT_AMOUNT": ("other", "The buyer says they were charged the wrong amount."),
}

# Evidence types (see docs/CONTRACTS.md EvidenceItem.type) per category.
# required items matter most; optional items strengthen the case.
CHECKLISTS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "not_received": {
        "required": [
            ("order_receipt", "Order receipt"),
            ("delivery_proof", "Delivery proof (tracking, photo, signature)"),
        ],
        "optional": [
            ("customer_message", "Customer communication"),
            ("refund_policy", "Refund / shipping policy shown at checkout"),
        ],
    },
    "unauthorized": {
        "required": [
            ("order_receipt", "Order receipt"),
            ("prior_orders", "Prior undisputed orders with matching email/IP/device"),
        ],
        "optional": [
            ("ip_device", "IP / device data for this order"),
            ("delivery_proof", "Delivery proof"),
            ("customer_message", "Customer communication"),
        ],
    },
    "not_as_described": {
        "required": [
            ("order_receipt", "Order receipt"),
            ("refund_policy", "Product description and return policy shown at checkout"),
        ],
        "optional": [
            ("customer_message", "Customer communication"),
            ("delivery_proof", "Delivery proof"),
        ],
    },
    "duplicate": {
        "required": [("order_receipt", "Receipts showing the charges are for separate orders")],
        "optional": [("customer_message", "Customer communication")],
    },
    "subscription_cancelled": {
        "required": [
            ("order_receipt", "Subscription terms and billing history"),
            ("customer_message", "Evidence of cancellation date (or lack of one)"),
        ],
        "optional": [("refund_policy", "Cancellation policy shown at signup")],
    },
    "refund_not_processed": {
        "required": [("order_receipt", "Order receipt and refund history")],
        "optional": [
            ("refund_policy", "Refund policy shown at checkout"),
            ("customer_message", "Customer communication"),
        ],
    },
    "other": {
        "required": [("order_receipt", "Order receipt")],
        "optional": [("customer_message", "Customer communication")],
    },
}


# Evidence that most changes the odds per dispute type. Beliefs and the scorer compare history on these.
KEY_EVIDENCE = {
    "not_received": {"delivery_photo"},
    "unauthorized": {"prior_orders"},
    "not_as_described": {"refund_policy"},
}
EVIDENCE_ALIAS = {"delivery_proof": "delivery_photo"}
EVIDENCE_LABEL = {
    "delivery_photo": "Delivery photo / proof",
    "prior_orders": "Prior undisputed orders",
    "refund_policy": "Checkout refund policy",
}


def strong_evidence(types: set[str], category: str) -> set[str]:
    return {EVIDENCE_ALIAS.get(x, x) for x in types} & KEY_EVIDENCE.get(category, set())
