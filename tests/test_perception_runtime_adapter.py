from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PERCEPTION_SRC = ROOT / "services" / "perception" / "src"
if str(PERCEPTION_SRC) not in sys.path:
    sys.path.insert(0, str(PERCEPTION_SRC))

from nztbdo_perception.runtime_adapter import RuntimePerceptionAdapter, WorldPointTracker


def test_runtime_adapter_returns_points_from_existing_frame(tmp_path: Path) -> None:
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x" * 123)  # size=123 -> 123 % 5 = 3 points

    adapter = RuntimePerceptionAdapter()
    points = adapter.detect_enemy_points(frame_path=str(frame), player_x=10.0, player_y=10.0)
    assert len(points) == 3


def test_runtime_adapter_falls_back_to_stub_when_model_missing(tmp_path: Path) -> None:
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x" * 101)  # size=101 -> 1 point in stub mode

    adapter = RuntimePerceptionAdapter(
        backend="ultralytics",
        model_path=str(tmp_path / "missing.pt"),
    )
    assert adapter.backend == "stub"
    points = adapter.detect_enemy_points(frame_path=str(frame), player_x=0.0, player_y=0.0)
    assert len(points) == 1


def test_world_tracker_keeps_stable_ids_on_small_motion() -> None:
    tracker = WorldPointTracker(match_distance=1.0, max_missed=3, smoothing=0.5)
    first = tracker.update([(10.0, 10.0), (20.0, 20.0)])
    second = tracker.update([(10.2, 10.1), (19.9, 20.1)])

    assert len(first) == 2
    assert len(second) == 2
    assert [t.track_id for t in first] == [t.track_id for t in second]
