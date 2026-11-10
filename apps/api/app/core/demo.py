"""Demo-only tools. Off unless DEMO_TOOLS is set; everything they do is marked as simulated.

`simulate_outcome` stands in for the bank's decision so the demo can show the agent learning from a
result without waiting weeks for a real one. It only works on a dispute the seller has already
responded to, and it records `processor_status = 'simulated:<outcome>'` so a simulated result can
never be mistaken for a real Stripe one.
"""

from typing import Literal

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.submissions import load_dispute
from app.settings import settings

Outcome = Literal["won", "lost"]
# Only after the seller responded: a response was approved (exported or sent) or submitted.
RESPONDED = {"approved", "submitted"}


def simulate_outcome(session: Session, dispute_id: str, outcome: Outcome) -> str:
    if not settings.demo_tools:
        raise ApiError(403, "demo_tools_disabled", "demo tools are turned off (set DEMO_TOOLS=1)")
    row = load_dispute(session, dispute_id, lock=True)
    if row.status not in RESPONDED:
        raise ApiError(
            409,
            "not_responded",
            "an outcome can only be simulated after a response was approved "
            f"(dispute is {row.status})",
        )
    row.status = outcome
    row.processor_status = f"simulated:{outcome}"
    session.commit()
    return row.status
