from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ORCH_SRC = ROOT / "services" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from nztbdo_orchestrator.calibration import generate_calibration_report


def test_calibration_reports_model_not_ready(tmp_path: Path) -> None:
    thresholds = tmp_path / "thresholds.yaml"
    thresholds.write_text(
        "perception:\n  runtime:\n    confidence_min: 0.45\n    enemy_class_ids: []\n",
        encoding="utf-8",
    )
    runtime_summary = {
        "perception_backend": "stub",
        "perception_model_exists": False,
        "perception_ultralytics_available": False,
        "detection_analytics": {
            "avg_confidence": 0.66,
            "min_confidence": 0.3,
            "max_confidence": 0.9,
            "class_counts": {"-1": 10},
        },
    }
    report = generate_calibration_report(
        runtime_summary=runtime_summary,
        thresholds_path=thresholds,
    )
    assert report["model_ready"] is False
    assert any("Model file missing" in item for item in report["findings"])
