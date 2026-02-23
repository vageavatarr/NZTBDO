from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
import sys


@dataclass(frozen=True)
class WindowCheck:
    title: str
    process_name: str
    pid: int
    allowed: bool
    reason: str


class WindowGuard:
    def __init__(
        self,
        *,
        allowed_titles: list[str] | None = None,
        allowed_processes: list[str] | None = None,
    ) -> None:
        self._allowed_titles = [v.lower() for v in (allowed_titles or []) if v]
        self._allowed_processes = [v.lower() for v in (allowed_processes or []) if v]

    @property
    def allowed_titles(self) -> list[str]:
        return list(self._allowed_titles)

    @property
    def allowed_processes(self) -> list[str]:
        return list(self._allowed_processes)

    def check(self) -> WindowCheck:
        title, pid = _foreground_title_pid()
        process = _process_name_from_pid(pid) if pid > 0 else ""
        if not self._allowed_titles and not self._allowed_processes:
            return WindowCheck(title=title, process_name=process, pid=pid, allowed=True, reason="no_constraints")

        title_ok = _matches_any(title, self._allowed_titles) if self._allowed_titles else True
        process_ok = _matches_any(process, self._allowed_processes) if self._allowed_processes else True
        allowed = title_ok and process_ok
        reason = "allowed" if allowed else "window_guard_blocked"
        return WindowCheck(title=title, process_name=process, pid=pid, allowed=allowed, reason=reason)


def _matches_any(value: str, patterns: list[str]) -> bool:
    normalized = value.lower()
    return any(pattern in normalized for pattern in patterns)


def _foreground_title_pid() -> tuple[str, int]:
    if sys.platform != "win32":
        return "", -1
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if hwnd == 0:
        return "", -1

    length = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if length > 0:
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value

    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return title, int(pid.value)


def _process_name_from_pid(pid: int) -> str:
    if sys.platform != "win32":
        return ""

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""

    try:
        size = ctypes.c_ulong(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) == 0:
            return ""
        return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(handle)
