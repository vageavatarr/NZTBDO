from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ORCH_SRC = ROOT / "services" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from nztbdo_orchestrator.window_guard import WindowGuard, _matches_any


class FakeGuard(WindowGuard):
    def __init__(self, title: str, process: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._process = process

    def check(self):  # type: ignore[override]
        title_ok = _matches_any(self._title, self.allowed_titles) if self.allowed_titles else True
        process_ok = _matches_any(self._process, self.allowed_processes) if self.allowed_processes else True
        allowed = title_ok and process_ok
        return {
            "allowed": allowed,
            "title": self._title,
            "process_name": self._process,
        }


def test_matches_any_case_insensitive() -> None:
    assert _matches_any("MyGameWindow", ["gamewindow"])
    assert not _matches_any("Notepad", ["gamewindow"])


def test_guard_constraints_title_and_process() -> None:
    guard = FakeGuard(
        title="Awesome GameWindow",
        process="game.exe",
        allowed_titles=["gamewindow"],
        allowed_processes=["game.exe"],
    )
    result = guard.check()
    assert result["allowed"] is True


def test_guard_blocks_when_constraints_miss() -> None:
    guard = FakeGuard(
        title="Browser",
        process="chrome.exe",
        allowed_titles=["gamewindow"],
        allowed_processes=["game.exe"],
    )
    result = guard.check()
    assert result["allowed"] is False
