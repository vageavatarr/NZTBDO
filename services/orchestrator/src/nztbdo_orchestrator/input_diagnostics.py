from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
from typing import Any

_ROOT = Path(__file__).resolve().parents[4]


def main() -> None:
    payload: dict[str, Any] = {
        "foreground": _foreground_info(),
        "self_process": _current_process_info(),
        "bdo_process": _find_process_info("BlackDesert64.exe"),
    }

    bdo = payload["bdo_process"]
    self_proc = payload["self_process"]
    recommendations: list[str] = []
    if not bdo.get("found", False):
        recommendations.append("BlackDesert64.exe process not found.")
    else:
        if bdo.get("integrity_level", 0) > self_proc.get("integrity_level", 0):
            recommendations.append("Run bot process with same or higher privilege level as Black Desert.")
        if bdo.get("is_minimized", False):
            recommendations.append("Restore game window (minimized windows often ignore input hooks).")
        if bdo.get("is_foreground", False) is False:
            recommendations.append("For stable skill tests keep BDO in foreground and borderless/windowed mode.")

    payload["recommendations"] = recommendations
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def _foreground_info() -> dict[str, Any]:
    user32 = ctypes.windll.user32
    hwnd = int(user32.GetForegroundWindow())
    if hwnd == 0:
        return {"hwnd": 0, "title": "", "pid": -1, "process_name": ""}
    title = _window_title(hwnd)
    pid = _pid_for_hwnd(hwnd)
    return {
        "hwnd": hwnd,
        "title": title,
        "pid": pid,
        "process_name": _process_name_from_pid(pid),
    }


def _current_process_info() -> dict[str, Any]:
    pid = os.getpid()
    return {
        "pid": pid,
        "process_name": _process_name_from_pid(pid),
        "integrity_level": _integrity_level_for_pid(pid),
    }


def _find_process_info(name: str) -> dict[str, Any]:
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-Process -Name '{name.replace('.exe', '')}' -ErrorAction SilentlyContinue | Select-Object -First 1 Id,ProcessName | ConvertTo-Json -Compress",
            ],
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        out = ""
    if not out:
        return {"found": False}
    try:
        row = json.loads(out)
        pid = int(row["Id"])
    except Exception:
        return {"found": False}

    hwnd = _top_hwnd_for_pid(pid)
    fg = int(ctypes.windll.user32.GetForegroundWindow())
    return {
        "found": True,
        "pid": pid,
        "process_name": _process_name_from_pid(pid),
        "integrity_level": _integrity_level_for_pid(pid),
        "hwnd": hwnd,
        "title": _window_title(hwnd) if hwnd else "",
        "is_minimized": _is_minimized(hwnd) if hwnd else False,
        "is_foreground": bool(hwnd and hwnd == fg),
    }


def _window_title(hwnd: int) -> str:
    if hwnd == 0:
        return ""
    user32 = ctypes.windll.user32
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _pid_for_hwnd(hwnd: int) -> int:
    user32 = ctypes.windll.user32
    pid_obj = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_obj))
    return int(pid_obj.value)


def _process_name_from_pid(pid: int) -> str:
    if pid <= 0:
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


def _integrity_level_for_pid(pid: int) -> int:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    TOKEN_QUERY = 0x0008
    TokenIntegrityLevel = 25
    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32
    advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(ctypes.c_ulong)

    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return 0
    token = ctypes.c_void_p()
    if advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)) == 0:
        kernel32.CloseHandle(process)
        return 0
    try:
        needed = ctypes.c_ulong(0)
        advapi32.GetTokenInformation(token, TokenIntegrityLevel, None, 0, ctypes.byref(needed))
        if needed.value == 0:
            return 0
        buf = (ctypes.c_byte * needed.value)()
        if advapi32.GetTokenInformation(token, TokenIntegrityLevel, ctypes.byref(buf), needed.value, ctypes.byref(needed)) == 0:
            return 0

        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_ulong)]

        class TOKEN_MANDATORY_LABEL(ctypes.Structure):
            _fields_ = [("Label", SID_AND_ATTRIBUTES)]

        tml = ctypes.cast(ctypes.byref(buf), ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
        sid = tml.Label.Sid
        count_ptr = advapi32.GetSidSubAuthorityCount(ctypes.c_void_p(sid))
        if not count_ptr:
            return 0
        idx = int(count_ptr.contents.value) - 1
        sub_auth_ptr = advapi32.GetSidSubAuthority(ctypes.c_void_p(sid), ctypes.c_ulong(idx))
        if not sub_auth_ptr:
            return 0
        return int(sub_auth_ptr.contents.value)
    finally:
        kernel32.CloseHandle(token)
        kernel32.CloseHandle(process)


def _top_hwnd_for_pid(pid: int) -> int:
    user32 = ctypes.windll.user32
    result = ctypes.c_void_p(0)
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        h = int(hwnd)
        if h == 0:
            return True
        this_pid = _pid_for_hwnd(h)
        if this_pid != pid:
            return True
        if user32.IsWindowVisible(h) == 0:
            return True
        result.value = h
        return False

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return int(result.value or 0)


def _is_minimized(hwnd: int) -> bool:
    if hwnd == 0:
        return False
    return bool(ctypes.windll.user32.IsIconic(hwnd))


if __name__ == "__main__":
    main()
