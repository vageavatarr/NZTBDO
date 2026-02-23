from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
NAV_SRC = ROOT / "services" / "navigation" / "src"
if str(NAV_SRC) not in sys.path:
    sys.path.insert(0, str(NAV_SRC))

from nztbdo_navigation.route_runner import RouteLoopRunner, Waypoint


def test_waypoint_advance() -> None:
    runner = RouteLoopRunner(
        waypoints=[
            Waypoint("wp_001", 0.0, 0.0, 1.0),
            Waypoint("wp_002", 10.0, 0.0, 1.0),
        ],
        stuck_timeout_sec=5.0,
    )
    status = runner.tick(pos_x=0.2, pos_y=0.1, in_combat=False)
    assert status.reached_waypoint is True
    assert status.current_waypoint_id == "wp_002"


def test_stuck_detected_when_no_progress() -> None:
    runner = RouteLoopRunner(
        waypoints=[Waypoint("wp_001", 100.0, 100.0, 0.5)],
        stuck_timeout_sec=0.05,
    )
    _ = runner.tick(pos_x=0.0, pos_y=0.0, in_combat=False)
    time.sleep(0.06)
    status = runner.tick(pos_x=0.0, pos_y=0.0, in_combat=False)
    assert status.stuck is True
    assert status.action == "recover"
