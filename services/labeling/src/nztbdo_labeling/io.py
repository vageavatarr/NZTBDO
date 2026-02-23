from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nztbdo_labeling.types import TickEvent


def read_tick_events(events_path: Path) -> list[TickEvent]:
    events: list[TickEvent] = []
    if not events_path.exists():
        return events

    with events_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event_type") != "tick":
                continue
            try:
                events.append(_to_tick_event(row))
            except (TypeError, ValueError, KeyError):
                continue
    return events


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")


def _to_tick_event(row: dict[str, Any]) -> TickEvent:
    execution = row.get("execution")
    exec_performed = False
    if isinstance(execution, dict):
        exec_performed = bool(execution.get("performed", False))

    input_data = row.get("input")
    if not isinstance(input_data, dict):
        input_data = {}

    navigation = row.get("navigation")
    if not isinstance(navigation, dict):
        navigation = None

    return TickEvent(
        session_id=str(row["session_id"]),
        timestamp_ms=int(row["timestamp_ms"]),
        fsm_state=str(row["fsm_state"]),
        action=str(row["action"]),
        reason=str(row["reason"]),
        execution_performed=exec_performed,
        input_data=input_data,
        navigation=navigation,
    )
