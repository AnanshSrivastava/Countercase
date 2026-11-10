"""MockShop matching and output rules. Pure: no database."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.core.collectors import DisputeContext, MockShop
from app.core.collectors.mock_shop_data import ORDERS
from app.core.hashing import customer_hash

SELLER = "sel_demo"
AFTER = datetime(2026, 10, 3, tzinfo=UTC)


def ctx(**overrides) -> DisputeContext:
    base = {
        "seller_id": SELLER,
        "dispute_id": "dp_x",
        "order_id": None,
        "customer_hash": "c_unknown",
        "amount": 4999,
        "currency": "usd",
        "created_at": AFTER,
    }
    return DisputeContext(**{**base, **overrides})


def types(collection) -> set[str]:
    return {i.type for i in collection.items}


def test_explicit_order_collects_full_picture() -> None:
    result = MockShop().collect(ctx(order_id="ord_101"))
    assert types(result) == {
        "order_receipt",
        "tracking",
        "delivery_proof",
        "ip_device",
        "refund_policy",
        "prior_orders",
    }
    assert (result.order_id, result.product_sku, result.courier) == (
        "ord_101",
        "SKU-TEE-04",
        "CourierX",
    )
    prior = next(i for i in result.items if i.type == "prior_orders")
    assert "2 prior undisputed orders" in prior.summary
    assert "ord_090" in prior.summary and "ord_095" in prior.summary


def test_order_with_customer_message_has_no_prior_orders() -> None:
    result = MockShop().collect(ctx(order_id="ord_102"))
    assert "customer_message" in types(result)
    assert "prior_orders" not in types(result)


def test_undelivered_order_has_no_delivery_proof() -> None:
    """Honest evidence: a parcel returned to sender must not produce delivery proof."""
    result = MockShop().collect(ctx(order_id="ord_103"))
    assert "delivery_proof" not in types(result)
    tracking = next(i for i in result.items if i.type == "tracking")
    assert "returned to sender" in tracking.summary


def test_unknown_explicit_order_never_falls_back_to_customer_match() -> None:
    buyer = customer_hash(SELLER, "buyer@example.com")
    result = MockShop().collect(ctx(order_id="ord_999", customer_hash=buyer, amount=4999))
    assert result.items == []


def test_customer_match_requires_exactly_one_order_with_same_amount() -> None:
    alex = customer_hash(SELLER, "alex@example.com")
    shop = MockShop()
    assert shop.collect(ctx(customer_hash=alex, amount=12900)).order_id == "ord_102"
    assert shop.collect(ctx(customer_hash=alex, amount=12901)).items == []  # amount differs
    assert shop.collect(ctx(customer_hash=alex, amount=12900, currency="eur")).items == []


def test_ambiguous_customer_match_attaches_nothing() -> None:
    alex = next(o for o in ORDERS if o.id == "ord_102")
    twin = replace(alex, id="ord_102b", tracking="CY777000999")
    shop = MockShop(orders=[alex, twin])
    ctx_alex = ctx(customer_hash=customer_hash(SELLER, alex.email), amount=alex.amount)
    assert shop.collect(ctx_alex).items == []


def test_order_placed_after_dispute_is_not_matched() -> None:
    alex = customer_hash(SELLER, "alex@example.com")
    early = datetime(2026, 9, 1, tzinfo=UTC)
    assert MockShop().collect(ctx(customer_hash=alex, amount=12900, created_at=early)).items == []


def test_other_sellers_get_nothing() -> None:
    assert MockShop().collect(ctx(seller_id="sel_other", order_id="ord_101")).items == []


@pytest.mark.parametrize("order", ORDERS, ids=lambda o: o.id)
def test_summaries_contain_no_personal_data(order) -> None:
    result = MockShop().collect(ctx(order_id=order.id))
    for item in result.items:
        assert "@" not in item.summary
        assert order.email not in item.summary
        assert order.email.split("@")[0] not in item.summary.lower().split()


def test_policy_summary_has_no_repeated_label_or_trailing_stop() -> None:
    """The agent adds its own 'Policy shown at checkout:' label and full stop around summaries."""
    policy = next(
        i for i in MockShop().collect(ctx(order_id="ord_101")).items if i.type == "refund_policy"
    )
    assert not policy.summary.startswith("Policy shown")
    assert not policy.summary.endswith(".")
