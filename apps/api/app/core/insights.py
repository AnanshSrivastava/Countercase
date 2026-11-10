"""GET /core/insights: root-cause dashboard numbers, rule-based tips and evidence readiness.

Facts only: every number comes from SQL over `disputes` / `evidence_items`, and every tip is a
fixed rule over those numbers. There is no LLM call anywhere in this module.

Definitions (also in the response field descriptions):
- closed = won, lost or accepted. open = everything else.
- fought = won or lost. win_rate = won / fought. loss_rate = lost / fought.
- accepted disputes are concessions; they count as closed but never as fought.
- Money is integer minor units in ONE currency (the seller's currency when it has disputes,
  otherwise the most common one). Disputes in other currencies are excluded everywhere and
  reported in `other_currencies`; currencies are never mixed.
- Evidence readiness counts only `verified = true` evidence, once per (dispute, type).
"""

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, distinct, func, literal_column, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tables import DisputeRow, EvidenceRow, SellerRow
from app.settings import settings

insights_router = APIRouter()
# Literal (not a bind parameter) so SELECT and GROUP BY render the identical expression.
CATEGORY_EXPR = func.coalesce(DisputeRow.category, literal_column("'unclassified'"))

CLOSED = ("won", "lost", "accepted")
# Seller notes and uploads are never verified (DB CHECK), so they are not listed as readiness.
READINESS_TYPES = (
    "order_receipt",
    "delivery_proof",
    "tracking",
    "ip_device",
    "prior_orders",
    "customer_message",
    "refund_policy",
)

MIN_FOUGHT_FOR_CATEGORY = 3  # below this a category win rate is marked low-confidence
MIN_CLOSED_FOR_GROUP = 2  # couriers / products need at least this many closed cases to rank
SMALL_GROUP = 5  # a courier / product group under this many fought cases is "small sample"
MAX_RANKED = 5
MAX_TIPS = 5

# Tip thresholds.
COURIER_MIN_FOUGHT = 3
COURIER_MARGIN = 0.15  # loss rate must exceed the overall loss rate by this much
CATEGORY_MAX_WIN_RATE = 0.4
EVIDENCE_GAP = 0.3  # evidence present on this much more of the won than of the lost cases
EVIDENCE_GAP_MIN_N = 3  # at least this many won AND lost cases to compare
PRODUCT_MIN_DISPUTES = 4
PRODUCT_MIN_SHARE = 0.3
PRODUCT_MIN_TOTAL = 8
LARGE_PERCENTILE = 0.75
LARGE_MIN_CLOSED = 8


class Counts(BaseModel):
    n_closed: int
    n_fought: int
    won: int
    lost: int
    accepted: int


class Headline(BaseModel):
    total_disputes: int
    open_disputes: int
    closed_disputes: int
    won: int
    lost: int
    accepted: int
    fought: int = Field(description="won + lost. This is the n behind win_rate.")
    win_rate: float | None = Field(description="won / fought; null when nothing was fought")
    money_at_stake_open: int = Field(description="Sum of amounts of open disputes")
    money_lost: int = Field(description="Sum of amounts of lost disputes")
    money_conceded: int = Field(description="Sum of amounts of accepted (not fought) disputes")
    money_recovered: int = Field(description="Sum of amounts of won disputes")
    total_disputed_amount: int = Field(description="Sum of amounts of all disputes, open or not")
    net_recovery_rate: float | None = Field(
        description="money_recovered / total_disputed_amount (open disputes still in the base)"
    )
    closed_disputed_amount: int
    net_recovery_rate_closed: float | None = Field(
        description="money_recovered / closed_disputed_amount (closed disputes only)"
    )


class ReasonStat(BaseModel):
    category: str
    count: int
    amount: int


class CategoryWinRate(Counts):
    category: str
    win_rate: float | None = Field(description="won / n_fought")
    low_confidence: bool = Field(description=f"True when n_fought < {MIN_FOUGHT_FOR_CATEGORY}")


class GroupStat(Counts):
    key: str
    loss_rate: float | None = Field(description="lost / n_fought")
    money_lost: int
    small_sample: bool = Field(description=f"True when n_fought < {SMALL_GROUP}")


class TipFact(BaseModel):
    label: str
    value: str


class Tip(BaseModel):
    id: str
    title: str
    evidence: list[TipFact] = Field(description="The numbers this tip is based on")
    action: str
    small_sample: bool
    sample_note: str | None = None


class EvidenceReadiness(BaseModel):
    type: str
    won_with: int
    won_total: int
    lost_with: int
    lost_total: int


class OtherCurrency(BaseModel):
    currency: str
    disputes: int


class Insights(BaseModel):
    seller_id: str
    currency: str = Field(description="All money fields are minor units of this currency")
    other_currencies: list[OtherCurrency] = Field(
        description="Disputes in other currencies, excluded from every number here"
    )
    headline: Headline
    top_reasons: list[ReasonStat]
    win_rate_by_category: list[CategoryWinRate]
    worst_couriers: list[GroupStat]
    worst_products: list[GroupStat]
    tips: list[Tip]
    evidence_readiness: list[EvidenceReadiness]


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _pct(num: int, den: int) -> str:
    return f"{round(100 * num / den)}%" if den else "n/a"


def _money(amount: int, currency: str) -> str:
    return f"{amount / 100:,.2f} {currency.upper()}"


def pick_currency(session: Session, seller_id: str) -> tuple[str, list[OtherCurrency]]:
    rows = session.execute(
        select(DisputeRow.currency, func.count())
        .where(DisputeRow.seller_id == seller_id)
        .group_by(DisputeRow.currency)
        .order_by(func.count().desc(), DisputeRow.currency)
    ).all()
    seller = session.get(SellerRow, seller_id)
    preferred = (seller.currency if seller else "usd").lower()
    present = {r[0].lower(): r[1] for r in rows}
    main = preferred if preferred in present else (rows[0][0].lower() if rows else preferred)
    others = [OtherCurrency(currency=c, disputes=n) for c, n in present.items() if c != main]
    return main, others


def _status_case(status: str) -> Any:
    return func.coalesce(func.sum(case((DisputeRow.status == status, 1), else_=0)), 0)


def _grouped(session: Session, key_col: Any, base: Sequence[Any]) -> dict[str, dict[str, int]]:
    """GROUP BY key: counts per outcome and the amount lost, for closed disputes."""
    lost_amount = func.coalesce(func.sum(case((DisputeRow.status == "lost", DisputeRow.amount))), 0)
    rows = session.execute(
        select(
            key_col,
            _status_case("won"),
            _status_case("lost"),
            _status_case("accepted"),
            lost_amount,
        )
        .where(*base, DisputeRow.status.in_(CLOSED), key_col.is_not(None))
        .group_by(key_col)
    ).all()
    return {
        str(k): {"won": int(w), "lost": int(lo), "accepted": int(a), "money_lost": int(m)}
        for k, w, lo, a, m in rows
    }


def _counts(d: dict[str, int]) -> Counts:
    return Counts(
        n_closed=d["won"] + d["lost"] + d["accepted"],
        n_fought=d["won"] + d["lost"],
        won=d["won"],
        lost=d["lost"],
        accepted=d["accepted"],
    )


def _group_stats(groups: dict[str, dict[str, int]]) -> list[GroupStat]:
    out = []
    for key, d in groups.items():
        c = _counts(d)
        if c.n_closed < MIN_CLOSED_FOR_GROUP or c.lost == 0:
            continue
        out.append(
            GroupStat(
                key=key,
                **c.model_dump(),
                loss_rate=_rate(c.lost, c.n_fought),
                money_lost=d["money_lost"],
                small_sample=c.n_fought < SMALL_GROUP,
            )
        )
    out.sort(key=lambda g: (-g.money_lost, -(g.loss_rate or 0), g.key))
    return out[:MAX_RANKED]


def _type_counts(
    session: Session, base: Sequence[Any], extra: Sequence[Any] = ()
) -> dict[tuple[str, str], int]:
    """Distinct verified (dispute, type) pairs per (type, won|lost)."""
    rows = session.execute(
        select(EvidenceRow.type, DisputeRow.status, func.count(distinct(DisputeRow.id)))
        .join(EvidenceRow, EvidenceRow.dispute_id == DisputeRow.id)
        .where(
            *base, *extra, EvidenceRow.verified.is_(True), DisputeRow.status.in_(("won", "lost"))
        )
        .group_by(EvidenceRow.type, DisputeRow.status)
    ).all()
    return {(t, s): int(n) for t, s, n in rows}


def _best_gap(
    with_counts: dict[tuple[str, str], int], won_total: int, lost_total: int, min_n: int
) -> tuple[str, int, int] | None:
    """Evidence type present on a clearly larger share of won than of lost cases."""
    if won_total < min_n or lost_total < min_n:
        return None
    best: tuple[float, str, int, int] | None = None
    for t in READINESS_TYPES:
        w, lo = with_counts.get((t, "won"), 0), with_counts.get((t, "lost"), 0)
        gap = w / won_total - lo / lost_total
        if gap >= EVIDENCE_GAP and (best is None or gap > best[0]):
            best = (gap, t, w, lo)
    return (best[1], best[2], best[3]) if best else None


def _label(t: str) -> str:
    return t.replace("_", " ")


def build_tips(
    session: Session,
    base: Sequence[Any],
    currency: str,
    head: Headline,
    couriers: dict[str, dict[str, int]],
    products: dict[str, dict[str, int]],
    categories: dict[str, dict[str, int]],
    evidence_counts: dict[tuple[str, str], int],
) -> list[Tip]:
    tips: list[Tip] = []
    overall_loss = _rate(head.lost, head.fought)

    # 1. A courier whose loss rate is clearly above the overall rate.
    if overall_loss is not None:
        cands = []
        for name, d in couriers.items():
            c = _counts(d)
            rate = _rate(c.lost, c.n_fought)
            if (
                c.n_fought >= COURIER_MIN_FOUGHT
                and c.lost >= 2
                and rate is not None
                and rate >= overall_loss + COURIER_MARGIN
            ):
                cands.append((d["money_lost"], rate, name, c))
        if cands:
            money, rate, name, c = max(cands, key=lambda x: (x[0], x[1]))
            tips.append(
                Tip(
                    id="courier_loss_rate",
                    title=f"{name} disputes are lost more often than your average",
                    evidence=[
                        TipFact(label=f"{name} loss rate", value=f"{_pct(c.lost, c.n_fought)}"),
                        TipFact(
                            label=f"{name} fought cases", value=f"{c.lost} lost of {c.n_fought}"
                        ),
                        TipFact(
                            label="Your overall loss rate",
                            value=f"{_pct(head.lost, head.fought)} ({head.lost} of {head.fought})",
                        ),
                        TipFact(label=f"Money lost on {name}", value=_money(money, currency)),
                    ],
                    action=(
                        f"Ask for signature or photo proof of delivery on {name} shipments, "
                        "or compare it with another carrier."
                    ),
                    small_sample=c.n_fought < SMALL_GROUP,
                    sample_note=_small_note(c.n_fought),
                )
            )

    # 2. A dispute type with a low win rate, plus the evidence that separates its wins from losses.
    if head.won + head.lost > 0:
        cands2 = []
        for cat, d in categories.items():
            c = _counts(d)
            rate = _rate(c.won, c.n_fought)
            if (
                c.n_fought >= MIN_FOUGHT_FOR_CATEGORY
                and rate is not None
                and rate <= CATEGORY_MAX_WIN_RATE
                and (head.win_rate is None or rate < head.win_rate)
            ):
                cands2.append((d["money_lost"], cat, c))
        if cands2:
            money, cat, c = max(cands2, key=lambda x: (x[0], x[1]))
            facts = [
                TipFact(label=f"{_label(cat)} win rate", value=f"{_pct(c.won, c.n_fought)}"),
                TipFact(label=f"{_label(cat)} fought cases", value=f"{c.won} won of {c.n_fought}"),
                TipFact(
                    label="Your overall win rate",
                    value=f"{_pct(head.won, head.fought)} ({head.won} of {head.fought})",
                ),
            ]
            by_cat = _type_counts(session, base, [DisputeRow.category == cat])
            gap = _best_gap(by_cat, c.won, c.lost, 1)
            action = (
                f"Review these cases before fighting similar {_label(cat)} disputes; "
                "consider accepting low-value ones."
            )
            if gap:
                t, w, lo = gap
                facts.append(
                    TipFact(
                        label=f"{_label(t)} on record",
                        value=f"{w} of {c.won} won vs {lo} of {c.lost} lost",
                    )
                )
                action = (
                    f"Collect {_label(t)} for {_label(cat)} disputes before responding; "
                    "it was present far more often on the cases you won."
                )
            tips.append(
                Tip(
                    id="category_low_win_rate",
                    title=f"You win few {_label(cat)} disputes",
                    evidence=facts,
                    action=action,
                    small_sample=c.n_fought < SMALL_GROUP,
                    sample_note=_small_note(c.n_fought),
                )
            )

    # 3. Many disputes on one product.
    if head.total_disputes >= PRODUCT_MIN_TOTAL:
        rows = session.execute(
            select(
                DisputeRow.product_sku, func.count(), func.coalesce(func.sum(DisputeRow.amount), 0)
            )
            .where(*base, DisputeRow.product_sku.is_not(None))
            .group_by(DisputeRow.product_sku)
            .order_by(func.count().desc(), DisputeRow.product_sku)
        ).first()
        if (
            rows
            and rows[1] >= PRODUCT_MIN_DISPUTES
            and rows[1] / head.total_disputes >= PRODUCT_MIN_SHARE
        ):
            sku, n, amount = rows
            c = _counts(products.get(sku, {"won": 0, "lost": 0, "accepted": 0}))
            tips.append(
                Tip(
                    id="product_concentration",
                    title=f"{sku} accounts for a large share of your disputes",
                    evidence=[
                        TipFact(
                            label=f"{sku} disputes",
                            value=f"{n} of {head.total_disputes} ({_pct(n, head.total_disputes)})",
                        ),
                        TipFact(
                            label=f"Amount disputed on {sku}", value=_money(int(amount), currency)
                        ),
                        TipFact(
                            label=f"{sku} closed outcomes",
                            value=f"{c.won} won, {c.lost} lost, {c.accepted} accepted",
                        ),
                    ],
                    action=(
                        f"Check the listing, packaging and description of {sku}; "
                        "a product problem is cheaper to fix than to dispute."
                    ),
                    small_sample=head.total_disputes < 20,
                    sample_note=(
                        f"Based on {head.total_disputes} disputes in total."
                        if head.total_disputes < 20
                        else None
                    ),
                )
            )

    # 4. Large not-received disputes closed without verified delivery proof.
    closed_amounts = [
        int(a)
        for a in session.scalars(
            select(DisputeRow.amount).where(*base, DisputeRow.status.in_(CLOSED))
        )
    ]
    if len(closed_amounts) >= LARGE_MIN_CLOSED:
        ordered = sorted(closed_amounts)
        threshold = ordered[min(len(ordered) - 1, int(LARGE_PERCENTILE * len(ordered)))]
        has_proof = (
            select(EvidenceRow.id)
            .where(
                EvidenceRow.dispute_id == DisputeRow.id,
                EvidenceRow.type == "delivery_proof",
                EvidenceRow.verified.is_(True),
            )
            .exists()
        )
        big = session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(case((~has_proof, 1), else_=0)), 0),
                func.coalesce(
                    func.sum(case((~has_proof & (DisputeRow.status == "lost"), 1), else_=0)), 0
                ),
            ).where(
                *base,
                DisputeRow.status.in_(CLOSED),
                DisputeRow.category == "not_received",
                DisputeRow.amount >= threshold,
            )
        ).one()
        n_big, n_missing, n_lost_missing = (int(x) for x in big)
        if n_missing >= 2 and n_lost_missing >= 1:
            tips.append(
                Tip(
                    id="large_without_delivery_proof",
                    title="Large not-received disputes were closed without delivery proof",
                    evidence=[
                        TipFact(
                            label="Large amount threshold (top quarter of closed)",
                            value=_money(threshold, currency),
                        ),
                        TipFact(label="Large not-received closed cases", value=str(n_big)),
                        TipFact(label="...without verified delivery proof", value=str(n_missing)),
                        TipFact(label="...of which lost", value=str(n_lost_missing)),
                    ],
                    action=(
                        "For high-value orders, ship with signature or photo confirmation so "
                        "delivery proof exists if the customer disputes."
                    ),
                    small_sample=n_big < SMALL_GROUP,
                    sample_note=_small_note(n_big),
                )
            )

    # 5. One evidence type is far more common on won than on lost disputes.
    gap = _best_gap(
        {(t, s): n for (t, s), n in evidence_counts.items()},
        head.won,
        head.lost,
        EVIDENCE_GAP_MIN_N,
    )
    if gap:
        t, w, lo = gap
        tips.append(
            Tip(
                id="evidence_gap",
                title=f"Winning disputes usually have {_label(t)}",
                evidence=[
                    TipFact(label=f"{_label(t)} on won disputes", value=f"{w} of {head.won}"),
                    TipFact(label=f"{_label(t)} on lost disputes", value=f"{lo} of {head.lost}"),
                ],
                action=f"Make collecting {_label(t)} a standard step for every dispute.",
                small_sample=min(head.won, head.lost) < SMALL_GROUP,
                sample_note=_small_note(min(head.won, head.lost)),
            )
        )
    return tips[:MAX_TIPS]


def _small_note(n: int) -> str | None:
    return (
        f"Small sample: only {n} fought cases, treat as a hint, not a finding."
        if n < SMALL_GROUP
        else None
    )


def compute_insights(session: Session, seller_id: str) -> Insights:
    currency, others = pick_currency(session, seller_id)
    base = [DisputeRow.seller_id == seller_id, func.lower(DisputeRow.currency) == currency]

    by_status = {
        s: (int(n), int(a))
        for s, n, a in session.execute(
            select(DisputeRow.status, func.count(), func.coalesce(func.sum(DisputeRow.amount), 0))
            .where(*base)
            .group_by(DisputeRow.status)
        )
    }

    def n(s: str) -> int:
        return by_status.get(s, (0, 0))[0]

    def amt(s: str) -> int:
        return by_status.get(s, (0, 0))[1]

    total = sum(c for c, _ in by_status.values())
    total_amount = sum(a for _, a in by_status.values())
    closed = sum(n(s) for s in CLOSED)
    closed_amount = sum(amt(s) for s in CLOSED)
    head = Headline(
        total_disputes=total,
        open_disputes=total - closed,
        closed_disputes=closed,
        won=n("won"),
        lost=n("lost"),
        accepted=n("accepted"),
        fought=n("won") + n("lost"),
        win_rate=_rate(n("won"), n("won") + n("lost")),
        money_at_stake_open=total_amount - closed_amount,
        money_lost=amt("lost"),
        money_conceded=amt("accepted"),
        money_recovered=amt("won"),
        total_disputed_amount=total_amount,
        net_recovery_rate=_rate(amt("won"), total_amount),
        closed_disputed_amount=closed_amount,
        net_recovery_rate_closed=_rate(amt("won"), closed_amount),
    )

    reasons = session.execute(
        select(
            CATEGORY_EXPR,
            func.count(),
            func.coalesce(func.sum(DisputeRow.amount), 0),
        )
        .where(*base)
        .group_by(CATEGORY_EXPR)
    ).all()
    top_reasons = sorted(
        (ReasonStat(category=c, count=int(k), amount=int(a)) for c, k, a in reasons),
        key=lambda r: (-r.count, -r.amount, r.category),
    )

    categories = _grouped(session, CATEGORY_EXPR, base)
    cat_rows = []
    for cat, d in categories.items():
        c = _counts(d)
        cat_rows.append(
            CategoryWinRate(
                category=cat,
                **c.model_dump(),
                win_rate=_rate(c.won, c.n_fought),
                low_confidence=c.n_fought < MIN_FOUGHT_FOR_CATEGORY,
            )
        )
    cat_rows.sort(key=lambda r: (-r.n_closed, r.category))

    couriers = _grouped(session, DisputeRow.courier, base)
    products = _grouped(session, DisputeRow.product_sku, base)

    counts = _type_counts(session, base)
    readiness = [
        EvidenceReadiness(
            type=t,
            won_with=counts.get((t, "won"), 0),
            won_total=head.won,
            lost_with=counts.get((t, "lost"), 0),
            lost_total=head.lost,
        )
        for t in READINESS_TYPES
    ]

    tips = build_tips(session, base, currency, head, couriers, products, categories, counts)
    return Insights(
        seller_id=seller_id,
        currency=currency,
        other_currencies=others,
        headline=head,
        top_reasons=top_reasons,
        win_rate_by_category=cat_rows,
        worst_couriers=_group_stats(couriers),
        worst_products=_group_stats(products),
        tips=tips,
        evidence_readiness=readiness,
    )


@insights_router.get("/insights", response_model=Insights)
def insights(
    seller_id: str | None = Query(default=None), session: Session = Depends(get_session)
) -> Insights:
    return compute_insights(session, seller_id or settings.default_seller_id)
