from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
TRAINING_SRC = ROOT / "services" / "training" / "src"
if str(TRAINING_SRC) not in sys.path:
    sys.path.insert(0, str(TRAINING_SRC))

from nztbdo_training.dataset_builder import build_flat_dataset


def test_build_flat_dataset_from_labels(tmp_path: Path) -> None:
    labels_file = tmp_path / "labels" / "session-123" / "episodes.jsonl"
    labels_file.parent.mkdir(parents=True, exist_ok=True)
    labels_file.write_text(json.dumps(_label_row()) + "\n", encoding="utf-8")

    out = tmp_path / "processed" / "dataset.jsonl"
    summary = build_flat_dataset(tmp_path / "labels", out)

    assert summary["rows"] == 1
    assert out.exists()
    line = out.read_text(encoding="utf-8").strip()
    row = json.loads(line)
    assert row["label_action_rationale"] == "single_target"
    assert row["action_press_3"] == 2


def _label_row() -> dict:
    return {
        "session_id": "session-123",
        "episode_id": "ep-1",
        "start_ts_ms": 1,
        "end_ts_ms": 2,
        "tick_count": 5,
        "label": {
            "action_rationale": "single_target",
            "outcome_quality": "good",
            "confidence": 0.8,
        },
        "stats": {
            "reasons": {"single_target": 2},
            "actions": {"press_3": 2},
            "performed_count": 4,
            "blocked_count": 1,
        },
        "context": {
            "first_input": {"engage_confidence": 0.7},
            "last_input": {"engage_confidence": 0.8},
        },
    }
