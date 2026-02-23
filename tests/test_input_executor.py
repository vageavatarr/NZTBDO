from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
INPUT_SRC = ROOT / "services" / "input-control" / "src"
if str(INPUT_SRC) not in sys.path:
    sys.path.insert(0, str(INPUT_SRC))

from nztbdo_input_control.executor import ActionExecutor


def test_rate_limit_blocks_fast_repeat() -> None:
    executor = ActionExecutor(max_hz=2, dry_run=True)
    first = executor.execute("press_1")
    second = executor.execute("press_1")

    assert first.performed is True
    assert second.performed is False
    assert second.reason == "rate_limited"


def test_rate_limit_allows_after_interval() -> None:
    executor = ActionExecutor(max_hz=10, dry_run=True)
    _ = executor.execute("press_2")
    time.sleep(0.12)
    second = executor.execute("press_2")
    assert second.performed is True
