from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


class SessionLogger:
    """Writes structured runtime events to JSONL files per session."""

    def __init__(self, base_dir: str | Path) -> None:
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        self._session_dir = Path(base_dir) / self.session_id
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._events_file = self._session_dir / "events.jsonl"

    @property
    def events_path(self) -> Path:
        return self._events_file

    def write_event(self, payload: dict[str, Any]) -> None:
        event = dict(payload)
        event.setdefault("session_id", self.session_id)
        line = json.dumps(event, ensure_ascii=True)
        with self._events_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def write_tick(
        self,
        *,
        timestamp_ms: int,
        fsm_state: str,
        tick_input: Any,
        action: str,
        reason: str,
        execution: Any,
    ) -> None:
        input_data = asdict(tick_input) if is_dataclass(tick_input) else dict(tick_input)
        exec_data = asdict(execution) if is_dataclass(execution) else dict(execution)
        self.write_event(
            {
                "event_type": "tick",
                "timestamp_ms": timestamp_ms,
                "fsm_state": fsm_state,
                "input": input_data,
                "action": action,
                "reason": reason,
                "execution": exec_data,
            }
        )
