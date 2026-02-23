from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SRC = ROOT / "services" / "capture" / "src"
if str(CAPTURE_SRC) not in sys.path:
    sys.path.insert(0, str(CAPTURE_SRC))

from nztbdo_capture.screen_capture import _select_primary_monitor


def test_selects_monitor_containing_origin() -> None:
    monitors = [
        {"left": -1920, "top": 0, "width": 3840, "height": 1080},  # virtual
        {"left": -1920, "top": 0, "width": 1920, "height": 1080},  # secondary
        {"left": 0, "top": 0, "width": 1920, "height": 1080},  # primary
    ]
    selected = _select_primary_monitor(monitors)
    assert selected["left"] == 0
    assert selected["top"] == 0
