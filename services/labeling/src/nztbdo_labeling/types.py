from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TickEvent:
    session_id: str
    timestamp_ms: int
    fsm_state: str
    action: str
    reason: str
    execution_performed: bool
    input_data: dict[str, Any]
    navigation: dict[str, Any] | None


@dataclass(frozen=True)
class Episode:
    session_id: str
    episode_id: str
    start_ts_ms: int
    end_ts_ms: int
    tick_count: int
    events: list[TickEvent]
