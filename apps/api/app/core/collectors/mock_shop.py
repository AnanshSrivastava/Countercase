"""Mock shop collector: reads the seeded store above through the EvidenceCollector interface.

Matching is deliberately strict (a wrong match would be fabricated evidence):
1. An explicit order id that the shop knows -> that order.
2. An explicit order id the shop does NOT know -> nothing (never fall back to a guess).
3. No order id: the one order from the same customer hash with the same amount and currency placed
   before the dispute was opened. Zero or several candidates -> nothing.
"""

from collections.abc import Iterable

from app.core.collectors.base import CollectedItem, Collection, DisputeContext
from app.core.collectors.mock_shop_data import (
    ORDERS,
    POLICY_VERSION_AT_CHECKOUT,
    Order,
    ShipEvent,
)
from app.core.hashing import customer_hash
from app.core.money import format_money

STATUS_TEXT = {
    "shipped": "shipped",
    "out_for_delivery": "out for delivery",
    "delivered": "delivered",
    "attempt_failed": "delivery attempt failed",
    "returned_to_sender": "returned to sender",
}


def _day(dt) -> str:
    return dt.strftime("%Y-%m-%d")


def _stamp(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _address_phrase(order: Order) -> str:
    return "matches" if order.address_matches_billing else "differs from"


class MockShop:
    def __init__(self, seller_id: str = "sel_demo", orders: Iterable[Order] = ORDERS) -> None:
        self.seller_id = seller_id
        self.orders = tuple(orders)

    # -- matching ---------------------------------------------------------------------------
    def find_order(self, ctx: DisputeContext) -> Order | None:
        if ctx.seller_id != self.seller_id:
            return None
        if ctx.order_id:
            return next((o for o in self.orders if o.id == ctx.order_id), None)
        candidates = [
            o
            for o in self.orders
            if customer_hash(ctx.seller_id, o.email) == ctx.customer_hash
            and o.amount == ctx.amount
            and o.currency == ctx.currency
            and o.placed_at <= ctx.created_at
        ]
        return candidates[0] if len(candidates) == 1 else None

    # -- collection -------------------------------------------------------------------------
    def collect(self, ctx: DisputeContext) -> Collection:
        order = self.find_order(ctx)
        if order is None:
            return Collection()

        items: list[CollectedItem] = [
            CollectedItem(
                type="order_receipt",
                source="shop_api",
                ref=f"{order.id}:receipt",
                summary=(
                    f"Order {order.id}: {order.product} ({order.sku}), "
                    f"{format_money(order.amount, order.currency)}, "
                    f"placed {_day(order.placed_at)}; "
                    f"shipping address {_address_phrase(order)} billing address"
                ),
                captured_at=order.placed_at,
            ),
            CollectedItem(
                type="tracking",
                source="shipping_api",
                ref=f"{order.id}:tracking",
                summary=f"{order.courier} tracking {order.tracking}: "
                + "; ".join(f"{STATUS_TEXT[e.status]} {_stamp(e.at)}" for e in order.events),
                captured_at=order.events[-1].at,
            ),
            CollectedItem(
                type="ip_device",
                source="shop_api",
                ref=f"{order.id}:ip_device",
                summary=f"Checkout for {order.id} from device {order.device} and IP {order.ip}",
                captured_at=order.placed_at,
            ),
            CollectedItem(
                type="refund_policy",
                source="shop_api",
                ref=f"{order.id}:policy",
                summary=POLICY_VERSION_AT_CHECKOUT.rstrip("."),
                captured_at=order.placed_at,
            ),
        ]

        delivered = next((e for e in order.events if e.status == "delivered"), None)
        if delivered:
            items.append(self._delivery_proof(order, delivered))

        prior = self._prior_orders(order)
        if prior:
            items.append(self._prior_orders_item(order, prior))

        for msg in order.messages:
            items.append(
                CollectedItem(
                    type="customer_message",
                    source="shop_api",
                    ref=msg.id,
                    summary=f"{_day(msg.at)}: {msg.summary}",
                    captured_at=msg.at,
                )
            )

        return Collection(
            items=items,
            order_id=order.id,
            product_sku=order.sku,
            courier=order.courier,
            tracking_number=order.tracking,
        )

    # -- helpers ----------------------------------------------------------------------------
    @staticmethod
    def _delivery_proof(order: Order, event: ShipEvent) -> CollectedItem:
        parts = [f"Delivered {_stamp(event.at)}"]
        if event.note:
            parts.append(event.note)
        if order.signed_by:
            parts.append(f"signed by {order.signed_by}")
        if order.delivery_photo:
            parts.append("courier delivery photo on record (not stored in this demo)")
        return CollectedItem(
            type="delivery_proof",
            source="shipping_api",
            ref=f"{order.id}:delivery",
            summary=", ".join(parts),
            captured_at=event.at,
        )

    def _prior_orders(self, order: Order) -> list[Order]:
        return [
            o
            for o in self.orders
            if o.email == order.email and o.placed_at < order.placed_at and not o.disputed
        ]

    @staticmethod
    def _prior_orders_item(order: Order, prior: list[Order]) -> CollectedItem:
        same_device = sum(1 for o in prior if o.device == order.device)
        same_ip = sum(1 for o in prior if o.ip == order.ip)
        ids = ", ".join(f"{o.id} ({_day(o.placed_at)})" for o in prior)
        return CollectedItem(
            type="prior_orders",
            source="shop_api",
            ref=f"{order.id}:prior",
            summary=(
                f"{len(prior)} prior undisputed order{'s' if len(prior) != 1 else ''} "
                "from the same "
                f"customer: {ids}; {same_device} used the same device and {same_ip} the same IP"
            ),
            captured_at=max(o.placed_at for o in prior),
        )
