from __future__ import annotations

from dataclasses import dataclass
import ctypes
import sys
import time


@dataclass(frozen=True)
class ExecutionResult:
    action: str
    performed: bool
    reason: str


class ActionExecutor:
    """Safety wrapper for action execution with rate limiting."""

    def __init__(
        self,
        max_hz: int = 8,
        dry_run: bool = True,
        allowed_window_substrings: list[str] | None = None,
    ) -> None:
        self._min_interval = 1.0 / max(max_hz, 1)
        self._last_action_ts = 0.0
        self._dry_run = dry_run
        self._allowed_windows = [item.lower() for item in (allowed_window_substrings or []) if item]

    def execute(self, action: str) -> ExecutionResult:
        now = time.monotonic()
        if action.startswith("press_"):
            if now - self._last_action_ts < self._min_interval:
                return ExecutionResult(action=action, performed=False, reason="rate_limited")
            emitted = self._emit_key_action(action)
            if emitted.performed:
                self._last_action_ts = now
            return emitted

        if action in {"patrol_move", "face_target", "resume_route", "reposition", "recover"}:
            return ExecutionResult(action=action, performed=True, reason="movement_intent")

        if action in {"idle", "wait_cd", "pause", "panic_stop"}:
            return ExecutionResult(action=action, performed=True, reason="no_key_action")

        return ExecutionResult(action=action, performed=False, reason="unknown_action")

    def _emit_key_action(self, action: str) -> ExecutionResult:
        key = action.removeprefix("press_")
        if key not in {"1", "2", "3", "4"}:
            return ExecutionResult(action=action, performed=False, reason="invalid_key")

        if not self._is_allowed_window():
            return ExecutionResult(action=action, performed=False, reason="window_not_allowed")

        if self._dry_run:
            return ExecutionResult(action=action, performed=True, reason="dry_run_key_emit")

        if sys.platform != "win32":
            return ExecutionResult(action=action, performed=False, reason="unsupported_platform")

        ok, fail_reason = self._send_key_windows(key)
        if not ok:
            return ExecutionResult(action=action, performed=False, reason=fail_reason)
        return ExecutionResult(action=action, performed=True, reason="key_emit")

    def _is_allowed_window(self) -> bool:
        if not self._allowed_windows:
            return True
        title = self._get_foreground_window_title().lower()
        if not title:
            return False
        return any(part in title for part in self._allowed_windows)

    def _get_foreground_window_title(self) -> str:
        if sys.platform != "win32":
            return ""
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd == 0:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def _send_key_windows(self, key: str) -> tuple[bool, str]:
        vk_map = {"1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34}
        vk = vk_map.get(key)
        if vk is None:
            return False, "invalid_key"

        # INPUT structures for SendInput (Windows API layout).
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort),
            ]

        class INPUTUNION(ctypes.Union):
            _fields_ = [
                ("ki", KEYBDINPUT),
                ("mi", MOUSEINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ii", INPUTUNION)]

        keydown = INPUT(
            type=1,
            ii=INPUTUNION(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0x0000, time=0, dwExtraInfo=0)),
        )
        keyup = INPUT(
            type=1,
            ii=INPUTUNION(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0x0002, time=0, dwExtraInfo=0)),
        )

        user32 = ctypes.windll.user32
        user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
        user32.SendInput.restype = ctypes.c_uint

        ctypes.windll.kernel32.SetLastError(0)
        sent_down = user32.SendInput(1, ctypes.byref(keydown), ctypes.sizeof(INPUT))
        err_down = ctypes.windll.kernel32.GetLastError()
        sent_up = user32.SendInput(1, ctypes.byref(keyup), ctypes.sizeof(INPUT))
        err_up = ctypes.windll.kernel32.GetLastError()
        if sent_down == 1 and sent_up == 1:
            return True, "key_emit"

        # Fallback for environments where SendInput is blocked (e.g., integrity mismatch).
        try:
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 0x0002, 0)
            return True, "key_emit_fallback"
        except Exception:
            pass

        code = err_up or err_down
        return False, f"sendinput_failed_{code}"
