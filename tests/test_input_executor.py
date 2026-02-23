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


class FakeExecutor(ActionExecutor):
    def __init__(self, title: str, send_ok: bool, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._send_ok = send_ok

    def _get_foreground_window_title(self) -> str:
        return self._title

    def _send_key_windows(self, key: str) -> bool:
        return self._send_ok


def test_window_allowlist_blocks_input() -> None:
    executor = FakeExecutor(
        title="Notepad",
        send_ok=True,
        max_hz=10,
        dry_run=False,
        allowed_window_substrings=["GameWindow"],
    )
    result = executor.execute("press_1")
    assert result.performed is False
    assert result.reason == "window_not_allowed"


def test_emit_when_window_allowed() -> None:
    executor = FakeExecutor(
        title="My GameWindow",
        send_ok=True,
        max_hz=10,
        dry_run=False,
        allowed_window_substrings=["GameWindow"],
    )
    result = executor.execute("press_1")
    assert result.performed is True
