# ruff: noqa: E501
"""F6 fight-or-accept scorer. Probability comes from counts, never from an LLM guess (IMPROVEMENTS #5).

Posterior mean of a Beta distribution whose prior is the shared-bank win rate with strength `prior_strength`
(pseudo-cases). With no seller history the result equals the prior, and the interval is wide.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

# Placeholder shared-bank win rates per category until the real shared-patterns bank is seeded.
DEFAULT_PRIOR = {
    "not_received": 0.45,
    "unauthorized": 0.30,
    "not_as_described": 0.40,
    "duplicate": 0.55,
    "subscription_cancelled": 0.40,
    "refund_not_processed": 0.25,
    "other": 0.35,
}


@dataclass(frozen=True)
class Advice:
    action: str  # "fight" | "accept"
    win_probability: float
    interval: tuple[float, float]
    n_cases: int
    basis: str
    amount_vs_cost: str
    rationale: list[str]


def win_probability(
    wins: int, losses: int, prior_rate: float, prior_strength: float = 4.0
) -> tuple[float, tuple[float, float]]:
    a = wins + prior_rate * prior_strength
    b = losses + (1 - prior_rate) * prior_strength
    n = a + b
    mean = a / n
    sd = sqrt(a * b / (n * n * (n + 1)))
    return mean, (max(0.0, mean - 1.645 * sd), min(1.0, mean + 1.645 * sd))


def advise(
    *,
    category: str,
    amount: int,
    currency: str,
    wins: int,
    losses: int,
    fee: int = 1500,
    effort_cost: int = 500,
    claim_looks_valid: bool = False,
    min_amount: int = 0,
    prior_rate: float | None = None,
) -> Advice:
    """amount, fee, effort_cost and min_amount are minor units. min_amount is a seller directive (e.g. never fight under X)."""
    prior = DEFAULT_PRIOR.get(category, 0.35) if prior_rate is None else prior_rate
    p, interval = win_probability(wins, losses, prior)
    n = wins + losses
    basis = "seller_history+shared_prior" if n else "generic"
    # Fighting costs effort always, and the dispute fee is forfeited when the fight is lost.
    expected_gain = p * amount - effort_cost - (1 - p) * fee
    money = f"Dispute {amount / 100:.2f} {currency.upper()} vs fee {fee / 100:.2f} and effort {effort_cost / 100:.2f}"
    reasons = [
        f"Estimated win chance {p:.0%} (range {interval[0]:.0%}-{interval[1]:.0%}) from {n} similar past case(s)."
        if n
        else f"No history yet; using the shared-pattern rate of {prior:.0%} for this dispute type."
    ]

    if claim_looks_valid:
        action = "accept"
        reasons.append(
            "The customer's claim appears valid based on the verified evidence; fighting is not recommended."
        )
    elif amount < min_amount:
        action = "accept"
        reasons.append("Below your minimum amount worth fighting (seller directive).")
    elif expected_gain <= 0:
        action = "accept"
        reasons.append(
            "Expected recovery does not cover the effort and the fee you forfeit on a loss."
        )
    else:
        action = "fight"
        reasons.append("Expected recovery exceeds the effort and fee at risk.")
    return Advice(
        action,
        round(p, 3),
        (round(interval[0], 3), round(interval[1], 3)),
        n,
        basis,
        money,
        reasons,
    )
