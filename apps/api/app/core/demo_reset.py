"""Reset the demo to a clean, known state (core data only).

    python -m app.core.demo_reset --yes        (make demo-reset)

Deletes every dispute that is not seeded history (ids `hist_*`), with their evidence, drafts,
submissions and uploaded files, then re-creates three live demo disputes through the normal webhook
path (so evidence is collected the same way as for a real one):
  ord_101  strong evidence            -> the agent recommends fighting
  ord_102  customer message on file    -> fight
  ord_103  returned to sender          -> the agent recommends accepting

It does NOT touch the seeded history (`make seed-core`) or the agent's memory (the agent owns that:
restart the api for the in-memory store, or `make seed` for Hindsight). Refuses to run unless
DEMO_TOOLS=1, because it deletes data.
"""

import argparse
import shutil
import sys
import time

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core import stripe_ingest
from app.core.stripe_ingest import ChargeInfo
from app.core.tables import DisputeRow, DraftRow, EvidenceRow, StripeEventRow, SubmissionRow
from app.settings import settings

HISTORY_PREFIX = "hist_"
DEMO_ORDERS = (("ord_101", 4999), ("ord_102", 12900), ("ord_103", 8400))
# The $129 story is due in 2 days, so the 72h deadline alert fires for it during the demo.
DUE_IN_DAYS = (4, 2, 6)


def reset(session: Session) -> int:
    """Wipe live data and re-create the demo disputes. Returns how many disputes were created."""
    if not settings.demo_tools:
        raise PermissionError("demo reset is disabled: set DEMO_TOOLS=1 to allow it")

    live = [d for (d,) in session.query(DisputeRow.id).all() if not d.startswith(HISTORY_PREFIX)]
    if live:
        for model in (SubmissionRow, DraftRow, EvidenceRow):
            session.execute(delete(model).where(model.dispute_id.in_(live)))
        session.execute(delete(DisputeRow).where(DisputeRow.id.in_(live)))
    session.execute(delete(StripeEventRow))
    session.commit()
    shutil.rmtree(settings.upload_dir, ignore_errors=True)

    now = int(time.time())
    for n, (order, amount) in enumerate(DEMO_ORDERS):
        event = {
            "id": f"evt_demo_{now}_{n}",
            "type": "charge.dispute.created",
            "created": now,
            "data": {
                "object": {
                    "id": f"du_demo_{order}_{now}",
                    "object": "dispute",
                    "amount": amount,
                    "currency": "usd",
                    "charge": f"ch_demo_{n}",
                    "reason": "product_not_received",
                    "status": "needs_response",
                    "created": now,
                    "evidence": {"customer_email_address": None},
                    "evidence_details": {"due_by": now + DUE_IN_DAYS[n] * 86400},
                    "metadata": {"order_id": order},
                }
            },
        }
        stripe_ingest.handle_event(session, event, lambda _charge: ChargeInfo())
    return len(DEMO_ORDERS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--yes", action="store_true", help="confirm that live demo data is deleted")
    if not parser.parse_args().yes:
        sys.exit("refusing to reset without --yes (this deletes live demo disputes)")
    from app.core.db import session_factory

    with session_factory()() as s:
        try:
            print(f"demo reset: {reset(s)} live disputes created; seeded history left untouched")
        except PermissionError as exc:
            sys.exit(str(exc))
