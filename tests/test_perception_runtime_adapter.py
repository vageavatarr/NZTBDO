from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PERCEPTION_SRC = ROOT / "services" / "perception" / "src"
if str(PERCEPTION_SRC) not in sys.path:
    sys.path.insert(0, str(PERCEPTION_SRC))

from nztbdo_perception.runtime_adapter import RuntimePerceptionAdapter


def test_runtime_adapter_returns_points_from_existing_frame(tmp_path: Path) -> None:
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"x" * 123)  # size=123 -> 123 % 5 = 3 points

    adapter = RuntimePerceptionAdapter()
    points = adapter.detect_enemy_points(frame_path=str(frame), player_x=10.0, player_y=10.0)
    assert len(points) == 3
