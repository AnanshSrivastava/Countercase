"""Seed data for the mock shop: a stand-in for a merchant's own store and courier systems.

This is the *source system*. Raw customer emails live here, not in Recoup's database:
core only ever stores per-seller HMAC hashes. SKUs and couriers match
data/seed/history.json so a fresh demo dispute lines up with the seeded memory.
IPs are RFC 5737 documentation addresses.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


@dataclass(frozen=True)
class ShipEvent:
    at: datetime
    status: str  # shipped | out_for_delivery | delivered | attempt_failed | returned_to_sender
    note: str = ""


@dataclass(frozen=True)
class Message:
    id: str
    at: datetime
    summary: str  # a neutral description, not the customer's raw text


@dataclass(frozen=True)
class Order:
    id: str
    email: str  # source-system data only
    placed_at: datetime
    amount: int
    currency: str
    sku: str
    product: str
    courier: str
    tracking: str
    events: tuple[ShipEvent, ...]
    ip: str
    device: str
    address_matches_billing: bool
    signed_by: str | None = None  # initials only
    delivery_photo: bool = False
    messages: tuple[Message, ...] = field(default_factory=tuple)
    disputed: bool = False


POLICY_VERSION_AT_CHECKOUT = (
    "Returns accepted within 7 days of delivery. Damaged or defective items are refunded or "
    "replaced if reported within 7 days of delivery. Shipping times are estimates."
)

ORDERS: tuple[Order, ...] = (
    # --- buyer@example.com: clean history, delivered with signature and photo
    Order(
        id="ord_090",
        email="buyer@example.com",
        placed_at=ts("2026-07-02T10:12:00"),
        amount=3200,
        currency="usd",
        sku="SKU-CAP-03",
        product="Canvas Cap",
        courier="CourierX",
        tracking="CX555000090",
        events=(ShipEvent(ts("2026-07-09T12:00:00"), "delivered"),),
        ip="203.0.113.58",
        device="d_buy1",
        address_matches_billing=True,
    ),
    Order(
        id="ord_095",
        email="buyer@example.com",
        placed_at=ts("2026-08-15T18:40:00"),
        amount=2800,
        currency="usd",
        sku="SKU-TEE-04",
        product="Logo Tee",
        courier="CourierX",
        tracking="CX555000095",
        events=(ShipEvent(ts("2026-08-20T15:30:00"), "delivered"),),
        ip="203.0.113.58",
        device="d_buy1",
        address_matches_billing=True,
    ),
    Order(
        id="ord_101",
        email="buyer@example.com",
        placed_at=ts("2026-09-12T09:30:00"),
        amount=4999,
        currency="usd",
        sku="SKU-TEE-04",
        product="Logo Tee (2 pack)",
        courier="CourierX",
        tracking="CX555000101",
        events=(
            ShipEvent(ts("2026-09-13T10:00:00"), "shipped"),
            ShipEvent(ts("2026-09-16T08:00:00"), "out_for_delivery"),
            ShipEvent(ts("2026-09-16T13:42:00"), "delivered", "signed at the door"),
        ),
        ip="203.0.113.58",
        device="d_buy1",
        address_matches_billing=True,
        signed_by="B. H.",
        delivery_photo=True,
    ),
    # --- alex@example.com: delivered, left at the door, customer wrote in beforehand
    Order(
        id="ord_102",
        email="alex@example.com",
        placed_at=ts("2026-09-14T17:05:00"),
        amount=12900,
        currency="usd",
        sku="SKU-MUG-01",
        product="Ceramic Mug Set",
        courier="CourierY",
        tracking="CY777000102",
        events=(
            ShipEvent(ts("2026-09-15T09:00:00"), "shipped"),
            ShipEvent(ts("2026-09-19T11:20:00"), "delivered", "left at front door"),
        ),
        ip="198.51.100.7",
        device="d_alex1",
        address_matches_billing=True,
        messages=(
            Message(
                "msg_2201",
                ts("2026-09-22T14:10:00"),
                "Customer wrote that the parcel had not arrived; "
                "shop replied the next day with the tracking link",
            ),
        ),
    ),
    # --- sam@example.com: never delivered. Honest evidence is thin, so accepting is the right call.
    Order(
        id="ord_103",
        email="sam@example.com",
        placed_at=ts("2026-09-18T20:10:00"),
        amount=8400,
        currency="usd",
        sku="SKU-BAG-07",
        product="Weekender Bag",
        courier="CourierZ",
        tracking="CZ999000103",
        events=(
            ShipEvent(ts("2026-09-19T09:30:00"), "shipped"),
            ShipEvent(ts("2026-09-23T10:15:00"), "attempt_failed", "recipient not available"),
            ShipEvent(ts("2026-09-28T08:00:00"), "returned_to_sender"),
        ),
        ip="192.0.2.44",
        device="d_sam1",
        address_matches_billing=False,
    ),
)
