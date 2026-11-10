# ruff: noqa: E501
import sys

from app.agent import seed_loader

sys.path.insert(0, str(seed_loader.HISTORY.parents[2] / "eval"))


def test_memory_on_beats_off_on_calibration():
    import run_eval

    res = run_eval.run(6)
    brier = {
        k: sum(x["brier"] for x in res["rows"][k]) / len(res["rows"][k]) for k in ("off", "on")
    }
    assert brier["on"] < brier["off"]
