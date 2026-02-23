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
    hwnd: int
    allowed: bool
    reason: str
    matched_in_background: bool = False


class WindowGuard:
    def __init__(
        self,
        *,
        allowed_titles: list[str] | None = None,
        allowed_processes: list[str] | None = None,
        require_foreground: bool = True,
    ) -> None:
        self._allowed_titles = [v.lower() for v in (allowed_titles or []) if v]
        self._allowed_processes = [v.lower() for v in (allowed_processes or []) if v]
        self._require_foreground = require_foreground

    @property
    def allowed_titles(self) -> list[str]:
        return list(self._allowed_titles)

    @property
    def allowed_processes(self) -> list[str]:
        return list(self._allowed_processes)

    def check(self) -> WindowCheck:
        title, pid, hwnd = _foreground_window()
        process = _process_name_from_pid(pid) if pid > 0 else ""
        if not self._allowed_titles and not self._allowed_processes:
            return WindowCheck(
                title=title,
                process_name=process,
                pid=pid,
                hwnd=hwnd,
                allowed=True,
                reason="no_constraints",
            )

        title_ok = _matches_any(title, self._allowed_titles) if self._allowed_titles else True
        process_ok = _matches_any(process, self._allowed_processes) if self._allowed_processes else True
        allowed = title_ok and process_ok
        if allowed:
            return WindowCheck(
                title=title,
                process_name=process,
                pid=pid,
                hwnd=hwnd,
                allowed=True,
                reason="allowed_foreground",
            )

        if self._require_foreground:
            return WindowCheck(
                title=title,
                process_name=process,
                pid=pid,
                hwnd=hwnd,
                allowed=False,
                reason="window_guard_blocked",
            )

        background_match = _find_matching_window(self._allowed_titles, self._allowed_processes)
        if background_match is None:
            return WindowCheck(
                title=title,
                process_name=process,
                pid=pid,
                hwnd=hwnd,
                allowed=False,
                reason="window_guard_blocked",
            )

        return WindowCheck(
            title=background_match.title,
            process_name=background_match.process_name,
            pid=background_match.pid,
            hwnd=background_match.hwnd,
            allowed=True,
            reason="allowed_background_bind",
            matched_in_background=True,
        )


def _matches_any(value: str, patterns: list[str]) -> bool:
    normalized = value.lower()
    return any(pattern in normalized for pattern in patterns)


def _foreground_window() -> tuple[str, int, int]:
    if sys.platform != "win32":
        return "", -1, 0
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if hwnd == 0:
        return "", -1, 0
    title = _window_title(hwnd)
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return title, int(pid.value), int(hwnd)


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


@dataclass(frozen=True)
class _WindowInfo:
    hwnd: int
    title: str
    pid: int
    process_name: str


def _window_title(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _find_matching_window(allowed_titles: list[str], allowed_processes: list[str]) -> _WindowInfo | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    matches: list[_WindowInfo] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, lparam) -> bool:
        if int(hwnd) == 0:
            return True
        pid_obj = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_obj))
        pid = int(pid_obj.value)
        if pid <= 0:
            return True
        process = _process_name_from_pid(pid)
        title = _window_title(int(hwnd))
        title_ok = _matches_any(title, allowed_titles) if allowed_titles else True
        process_ok = _matches_any(process, allowed_processes) if allowed_processes else True
        if title_ok and process_ok:
            matches.append(_WindowInfo(hwnd=int(hwnd), title=title, pid=pid, process_name=process))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return matches[0] if matches else None
