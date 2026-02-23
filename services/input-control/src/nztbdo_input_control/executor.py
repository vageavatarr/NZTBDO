from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass(frozen=True)
class ExecutionResult:
    action: str
    performed: bool
    reason: str


class ActionExecutor:
    """Safety wrapper for action execution with rate limiting."""

    def __init__(self, max_hz: int = 8, dry_run: bool = True) -> None:
        self._min_interval = 1.0 / max(max_hz, 1)
        self._last_action_ts = 0.0
        self._dry_run = dry_run

    def execute(self, action: str) -> ExecutionResult:
        now = time.monotonic()
        if action.startswith("press_"):
            if now - self._last_action_ts < self._min_interval:
                return ExecutionResult(action=action, performed=False, reason="rate_limited")
            self._last_action_ts = now
            return self._emit_key_action(action)

        if action in {"patrol_move", "face_target", "resume_route", "reposition", "recover"}:
            return ExecutionResult(action=action, performed=True, reason="movement_intent")

        if action in {"idle", "wait_cd", "pause", "panic_stop"}:
            return ExecutionResult(action=action, performed=True, reason="no_key_action")

        return ExecutionResult(action=action, performed=False, reason="unknown_action")

    def _emit_key_action(self, action: str) -> ExecutionResult:
        key = action.removeprefix("press_")
        if key not in {"1", "2", "3", "4"}:
            return ExecutionResult(action=action, performed=False, reason="invalid_key")

        # Real key emission can be plugged here (SendInput/win32 API).
        if self._dry_run:
            return ExecutionResult(action=action, performed=True, reason="dry_run_key_emit")

        return ExecutionResult(action=action, performed=False, reason="not_implemented")
