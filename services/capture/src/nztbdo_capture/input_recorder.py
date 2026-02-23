from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Any

from nztbdo_capture.chunked_writer import ChunkedJsonlWriter


@dataclass(frozen=True)
class KeyboardEvent:
    key: str
    event_type: str  # down/up
    timestamp_ms: int


@dataclass(frozen=True)
class MouseEvent:
    x: int
    y: int
    button: str
    event_type: str  # move/down/up/scroll
    timestamp_ms: int


class InputTelemetryRecorder:
    """Records keyboard/mouse/window telemetry into chunked JSONL files."""

    def __init__(self, output_dir: str, chunk_size: int = 1000) -> None:
        self._writer = ChunkedJsonlWriter(output_dir=output_dir, chunk_size=chunk_size)

    def record_keyboard(self, key: str, event_type: str) -> None:
        event = KeyboardEvent(
            key=key,
            event_type=event_type,
            timestamp_ms=_now_ms(),
        )
        self._writer.write(
            {
                "event_type": "keyboard",
                "payload": asdict(event),
            }
        )

    def record_mouse(self, x: int, y: int, button: str, event_type: str) -> None:
        event = MouseEvent(
            x=x,
            y=y,
            button=button,
            event_type=event_type,
            timestamp_ms=_now_ms(),
        )
        self._writer.write(
            {
                "event_type": "mouse",
                "payload": asdict(event),
            }
        )

    def record_window(self, title: str, process: str, rect: dict[str, int]) -> None:
        self._writer.write(
            {
                "event_type": "window",
                "payload": {
                    "title": title,
                    "process": process,
                    "rect": rect,
                    "timestamp_ms": _now_ms(),
                },
            }
        )

    def record_frame_meta(self, frame_id: str, width: int, height: int, path: str) -> None:
        self._writer.write(
            {
                "event_type": "frame_meta",
                "payload": {
                    "frame_id": frame_id,
                    "width": width,
                    "height": height,
                    "path": path,
                    "timestamp_ms": _now_ms(),
                },
            }
        )

    def close(self) -> None:
        self._writer.close()


def _now_ms() -> int:
    return int(time.time() * 1000)
