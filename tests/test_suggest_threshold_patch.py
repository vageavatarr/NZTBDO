from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ORCH_SRC = ROOT / "services" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from nztbdo_orchestrator.suggest_threshold_patch import _apply_recommendations


def test_apply_recommendations_updates_runtime_fields() -> None:
    thresholds = {
        "perception": {
            "runtime": {
                "confidence_min": 0.5,
                "enemy_class_ids": [],
            }
        }
    }
    calibration = {
        "recommendations": {
            "perception.runtime.confidence_min": 0.42,
            "perception.runtime.enemy_class_ids": [2, 5, 9],
        }
    }
    out, changed = _apply_recommendations(thresholds, calibration)
    assert changed is True
    runtime = out["perception"]["runtime"]
    assert runtime["confidence_min"] == 0.42
    assert runtime["enemy_class_ids"] == [2, 5, 9]
