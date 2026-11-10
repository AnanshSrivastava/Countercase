"""Freeze the agent's real drafts (memory ON and OFF) for the demo disputes into fixtures/drafts/.

Why: if the live model/Hindsight is slow or down on demo day, run the web app with
NEXT_PUBLIC_USE_FIXTURES=1 and it serves exactly these files (same shapes as the live API).

    MEMORY_BACKEND=hindsight python eval/cache_demo.py        (or leave unset for the in-memory demo history)
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from app.agent import seed_loader  # noqa: E402
from app.agent.router import get_source, get_store  # noqa: E402
from app.main import app  # noqa: E402
from app.settings import settings  # noqa: E402

DISPUTES = ["dp_001", "dp_002", "dp_003"]


def main() -> None:
    if settings.memory_backend == "inmemory":  # give the in-memory store the full demo history
        seed_loader.load(get_store(), json.loads(seed_loader.HISTORY.read_text(encoding="utf-8")))
    client = TestClient(app)
    out = ROOT / "fixtures" / "drafts"
    for dispute_id in DISPUTES:
        if get_source().get(dispute_id) is None:
            print(f"skip {dispute_id}: not found (run `make seed-fixtures`)")
            continue
        for mode in ("off", "on"):
            r = client.post(f"/agent/disputes/{dispute_id}/draft", params={"memory": mode})
            r.raise_for_status()
            (out / f"{dispute_id}_memory_{mode}.json").write_text(
                json.dumps(r.json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            a = r.json()["advice"]
            print(f"{dispute_id} memory={mode}: {a['action']} {a['win_probability']:.0%} (n={a['n_cases']})")


if __name__ == "__main__":
    main()
