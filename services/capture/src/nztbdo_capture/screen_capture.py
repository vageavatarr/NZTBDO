from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any


@dataclass(frozen=True)
class FrameCaptureResult:
    frame_id: str
    timestamp_ms: int
    width: int
    height: int
    path: str


class PrimaryMonitorCapture:
    """Captures frames only from the primary monitor."""

    def __init__(self) -> None:
        try:
            import mss  # type: ignore
            import mss.tools  # type: ignore
        except ImportError as exc:
            raise RuntimeError("mss is required for screen capture. Install with: pip install mss") from exc
        self._mss_module = mss
        self._session = mss.mss()
        self._primary = _select_primary_monitor(self._session.monitors)

    @property
    def primary_monitor(self) -> dict[str, int]:
        return {
            "left": int(self._primary["left"]),
            "top": int(self._primary["top"]),
            "width": int(self._primary["width"]),
            "height": int(self._primary["height"]),
        }

    def capture_to_png(self, frames_dir: Path, prefix: str, index: int) -> FrameCaptureResult:
        frames_dir.mkdir(parents=True, exist_ok=True)
        timestamp_ms = int(time.time() * 1000)
        frame_id = f"{prefix}_{index:06d}"
        path = frames_dir / f"{frame_id}.png"

        raw = self._session.grab(self._primary)
        self._mss_module.tools.to_png(raw.rgb, raw.size, output=str(path))

        return FrameCaptureResult(
            frame_id=frame_id,
            timestamp_ms=timestamp_ms,
            width=int(raw.size[0]),
            height=int(raw.size[1]),
            path=str(path),
        )

    def close(self) -> None:
        close_fn = getattr(self._session, "close", None)
        if callable(close_fn):
            close_fn()


def _select_primary_monitor(monitors: list[dict[str, Any]]) -> dict[str, Any]:
    if len(monitors) <= 1:
        raise ValueError("No physical monitors found in mss monitor list")

    # mss monitors[1:] are physical displays. Primary monitor typically contains (0, 0).
    for monitor in monitors[1:]:
        left = int(monitor["left"])
        top = int(monitor["top"])
        width = int(monitor["width"])
        height = int(monitor["height"])
        if left <= 0 < left + width and top <= 0 < top + height:
            return monitor

    # Fallback: first physical monitor.
    return monitors[1]
