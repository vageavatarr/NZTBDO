from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
LABELING_SRC = ROOT / "services" / "labeling" / "src"
if str(LABELING_SRC) not in sys.path:
    sys.path.insert(0, str(LABELING_SRC))

from nztbdo_labeling.pipeline import run_labeling_for_session


def test_labeling_generates_episode_rows(tmp_path: Path) -> None:
    session_dir = tmp_path / "logs" / "session-001"
    session_dir.mkdir(parents=True, exist_ok=True)
    events_file = session_dir / "events.jsonl"

    rows = [
        _tick("session-001", 1000, "PATROL", "patrol_move", "route_follow", True),
        _tick("session-001", 1100, "COMBAT", "press_1", "front_aoe", True),
        _tick("session-001", 1200, "COMBAT", "press_3", "single_target", False),
        _tick("session-001", 1300, "POST_COMBAT", "resume_route", "area_clear", True),
    ]
    with events_file.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    summary = run_labeling_for_session(
        events_path=events_file,
        labels_root=tmp_path / "labels",
        pre_ticks=1,
        post_ticks=1,
    )
    assert summary.events_total == 4
    assert summary.episodes_total == 1
    assert summary.output_path.exists()

    lines = summary.output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    label_row = json.loads(lines[0])
    assert label_row["label"]["action_rationale"] in {"aoe_front", "single_target"}
    assert label_row["label"]["outcome_quality"] in {"good", "neutral", "bad"}


def _tick(
    session_id: str,
    ts: int,
    state: str,
    action: str,
    reason: str,
    performed: bool,
) -> dict:
    return {
        "event_type": "tick",
        "session_id": session_id,
        "timestamp_ms": ts,
        "fsm_state": state,
        "action": action,
        "reason": reason,
        "execution": {"action": action, "performed": performed, "reason": "x"},
        "input": {},
        "navigation": None,
    }
