"""PayPalCollector: verified facts from PayPal's own records, merged with the shop collector.

Never fabricates (collector rule 1): if the transaction cannot be matched with certainty, PayPal
contributes nothing. A PayPal failure never hides the shop evidence, and vice versa.
"""

from __future__ import annotations

import logging
from datetime import UTC

from app.core.collectors.base import (
    CollectedItem,
    Collection,
    DisputeContext,
    EvidenceCollector,
)
from app.core.money import format_money
from app.core.paypal.client import PayPalClient, PayPalError
from app.core.paypal.mapping import parse_ts

log = logging.getLogger(__name__)


class PayPalCollector:
    def __init__(self, client: PayPalClient, shop: EvidenceCollector | None = None) -> None:
        self.client, self.shop = client, shop

    def collect(self, ctx: DisputeContext) -> Collection:
        result = self.shop.collect(ctx) if self.shop else Collection()
        item = self._receipt(ctx)
        if item:
            result.items.insert(0, item)
        return result

    def _receipt(self, ctx: DisputeContext) -> CollectedItem | None:
        if not ctx.processor_charge_id or not self.client.available()[0]:
            return None
        try:
            detail = self.client.get_transaction(ctx.processor_charge_id, ctx.created_at)
        except PayPalError:
            log.warning("paypal transaction lookup failed for %s", ctx.dispute_id, exc_info=True)
            return None
        if not detail:
            return None
        info = detail.get("transaction_info") or {}
        gross = info.get("transaction_amount") or {}
        if not info.get("transaction_id") or not gross.get("value"):
            return None
        from app.core.paypal.mapping import to_minor

        cur = gross.get("currency_code", ctx.currency)
        when = parse_ts(info.get("transaction_initiation_date"))
        shipped_to = "present" if (detail.get("shipping_info") or {}).get("address") else "absent"
        return CollectedItem(
            type="order_receipt",
            source="paypal",
            ref=f"{info['transaction_id']}:receipt",
            summary=(
                f"PayPal transaction {info['transaction_id']}: "
                f"{format_money(to_minor(gross['value'], cur), cur)}, "
                f"status {info.get('transaction_status', 'unknown')}, "
                f"initiated {when.astimezone(UTC).strftime('%Y-%m-%d') if when else 'unknown'}; "
                f"shipping address on the transaction is {shipped_to}"
            ),
            captured_at=when or ctx.created_at,
        )
