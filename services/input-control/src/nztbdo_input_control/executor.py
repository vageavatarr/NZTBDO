from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
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
        allowed_process_names: list[str] | None = None,
        bind_to_process: bool = False,
        allow_background_input: bool = False,
        force_activate_before_input: bool = False,
        post_skill_pause_sec: float = 1.5,
        post_move_skill_block_sec: float = 0.5,
    ) -> None:
        self._min_interval = 1.0 / max(max_hz, 1)
        self._last_action_ts = 0.0
        self._last_skill_ts = 0.0
        self._last_move_ts = 0.0
        self._dry_run = dry_run
        self._allowed_windows = [item.lower() for item in (allowed_window_substrings or []) if item]
        self._allowed_processes = [item.lower() for item in (allowed_process_names or []) if item]
        self._bind_to_process = bind_to_process
        self._allow_background_input = allow_background_input
        self._force_activate_before_input = force_activate_before_input
        self._post_skill_pause_sec = max(0.0, float(post_skill_pause_sec))
        self._post_move_skill_block_sec = max(0.0, float(post_move_skill_block_sec))

    def execute(self, action: str) -> ExecutionResult:
        now = time.monotonic()
        if action.startswith("press_"):
            if now - self._last_action_ts < self._min_interval:
                return ExecutionResult(action=action, performed=False, reason="rate_limited")
            if now - self._last_skill_ts < self._post_skill_pause_sec:
                return ExecutionResult(action=action, performed=False, reason="post_skill_pause")
            if now - self._last_move_ts < self._post_move_skill_block_sec:
                return ExecutionResult(action=action, performed=False, reason="post_move_guard")
            emitted = self._emit_key_action(action)
            if emitted.performed:
                self._last_action_ts = now
                self._last_skill_ts = now
            return emitted

        if action in {"patrol_move", "face_target", "resume_route", "reposition", "recover"}:
            self._last_move_ts = now
            return ExecutionResult(action=action, performed=True, reason="movement_intent")

        if action in {"idle", "wait_cd", "pause", "panic_stop"}:
            return ExecutionResult(action=action, performed=True, reason="no_key_action")

        return ExecutionResult(action=action, performed=False, reason="unknown_action")

    def _emit_key_action(self, action: str) -> ExecutionResult:
        key = action.removeprefix("press_")

        allowed, target_hwnd = self._resolve_target_window()
        if not allowed:
            return ExecutionResult(action=action, performed=False, reason="window_not_allowed")

        if self._dry_run:
            return ExecutionResult(action=action, performed=True, reason="dry_run_key_emit")

        if sys.platform != "win32":
            return ExecutionResult(action=action, performed=False, reason="unsupported_platform")

        foreground_hwnd = self._get_foreground_hwnd()
        if self._bind_to_process and target_hwnd != 0 and foreground_hwnd != target_hwnd:
            if self._activate_window(target_hwnd):
                foreground_hwnd = self._get_foreground_hwnd()

        if self._force_activate_before_input and target_hwnd != 0:
            self._activate_window(target_hwnd)
            foreground_hwnd = self._get_foreground_hwnd()

        use_background = self._allow_background_input and target_hwnd != 0 and target_hwnd != foreground_hwnd
        if use_background:
            ok, fail_reason = self._send_action_background(target_hwnd, key)
            if ok:
                return ExecutionResult(action=action, performed=True, reason="key_emit_background")
            if self._activate_window(target_hwnd):
                ok2, fail_reason2 = self._send_action_windows(key)
                if ok2:
                    return ExecutionResult(action=action, performed=True, reason="key_emit_bound_window")
                return ExecutionResult(action=action, performed=False, reason=fail_reason2)
        else:
            ok, fail_reason = self._send_action_windows(key)
        if not ok:
            return ExecutionResult(action=action, performed=False, reason=fail_reason)
        return ExecutionResult(action=action, performed=True, reason="key_emit")

    def _resolve_target_window(self) -> tuple[bool, int]:
        if sys.platform != "win32":
            return True, 0
        if not self._allowed_windows and not self._allowed_processes:
            return True, self._get_foreground_hwnd()

        fg_hwnd = self._get_foreground_hwnd()
        fg_title = self._get_window_title(fg_hwnd)
        fg_process = self._get_process_name_for_hwnd(fg_hwnd)
        if self._matches_constraints(fg_title, fg_process):
            return True, fg_hwnd

        if self._bind_to_process:
            hwnd = self._find_allowed_window_hwnd()
            if hwnd != 0:
                return True, hwnd
        return False, 0

    def _matches_constraints(self, title: str, process: str) -> bool:
        title_ok = any(part in title.lower() for part in self._allowed_windows) if self._allowed_windows else True
        process_ok = any(part in process.lower() for part in self._allowed_processes) if self._allowed_processes else True
        return title_ok and process_ok

    def _get_foreground_window_title(self) -> str:
        return self._get_window_title(self._get_foreground_hwnd())

    def _get_foreground_hwnd(self) -> int:
        if sys.platform != "win32":
            return 0
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        return int(hwnd)

    def _get_window_title(self, hwnd: int) -> str:
        if sys.platform != "win32" or hwnd == 0:
            return ""
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def _activate_window(self, hwnd: int) -> bool:
        if sys.platform != "win32" or hwnd == 0:
            return False
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        try:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.03)
            return self._get_foreground_hwnd() == hwnd
        except Exception:
            return False

    def _get_process_name_for_hwnd(self, hwnd: int) -> str:
        if sys.platform != "win32" or hwnd == 0:
            return ""
        user32 = ctypes.windll.user32
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return self._process_name_from_pid(int(pid.value))

    def _process_name_from_pid(self, pid: int) -> str:
        if sys.platform != "win32" or pid <= 0:
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

    def _find_allowed_window_hwnd(self) -> int:
        if sys.platform != "win32":
            return 0
        user32 = ctypes.windll.user32
        result = ctypes.c_void_p(0)

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd, lparam) -> bool:
            h = int(hwnd)
            if h == 0:
                return True
            title = self._get_window_title(h)
            process = self._get_process_name_for_hwnd(h)
            if self._matches_constraints(title, process):
                result.value = h
                return False
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return int(result.value or 0)

    def _send_action_windows(self, key: str) -> tuple[bool, str]:
        if key in {"1", "2", "3", "4"}:
            return self._send_key_windows(key)
        if key == "shift_q":
            return self._send_shift_key("q")
        if key == "hold_q_4s":
            return self._send_hold_key("q", hold_sec=4.0)
        if key == "shift_q_q":
            return self._send_shift_q_q()
        if key == "shift_rmb_hold":
            return self._send_shift_rmb_hold(hold_sec=2.5)
        if key == "shift_lmb":
            return self._send_shift_mouse_click(left=True)
        if key == "shift_f":
            return self._send_shift_key("f")
        if key == "s_lmb":
            return self._send_s_lmb()
        if key == "lmb":
            return self._send_lmb()
        return False, "invalid_key"

    def _send_action_background(self, hwnd: int, key: str) -> tuple[bool, str]:
        if hwnd == 0:
            return False, "no_target_window"
        if key in {"1", "2", "3", "4"}:
            vk = {"1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34}[key]
            return self._post_key_tap(hwnd, vk, reason="bg_key_tap")
        if key == "shift_q":
            return self._post_shift_key(hwnd, 0x51, reason="bg_shift_q")
        if key == "hold_q_4s":
            return self._post_key_hold(hwnd, 0x51, hold_sec=4.0, reason="bg_hold_q_4s")
        if key == "shift_q_q":
            ok1, _ = self._post_shift_key(hwnd, 0x51, reason="bg_shift_q_1")
            time.sleep(0.04)
            ok2, _ = self._post_shift_key(hwnd, 0x51, reason="bg_shift_q_2")
            return (ok1 and ok2), "bg_shift_q_q"
        if key == "shift_rmb_hold":
            return self._post_shift_mouse_hold(hwnd, right=True, hold_sec=2.5, reason="bg_shift_rmb_hold")
        if key == "shift_lmb":
            return self._post_shift_mouse_click(hwnd, left=True, reason="bg_shift_lmb")
        if key == "shift_f":
            return self._post_shift_key(hwnd, 0x46, reason="bg_shift_f")
        if key == "s_lmb":
            return self._post_s_lmb(hwnd, reason="bg_s_lmb")
        if key == "lmb":
            return self._post_lmb(hwnd, reason="bg_lmb")
        return False, "invalid_key"

    def _send_key_windows(self, key: str) -> tuple[bool, str]:
        vk_map = {"1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34}
        vk = vk_map.get(key)
        if vk is None:
            return False, "invalid_key"
        return self._tap_key(vk)

    def _send_shift_q_q(self) -> tuple[bool, str]:
        VK_Q = 0x51
        try:
            self._set_key_state(VK_SHIFT := 0xA0, keyup=False)
            time.sleep(0.01)
            ok1, _ = self._tap_key(VK_Q)
            time.sleep(0.04)
            ok2, _ = self._tap_key(VK_Q)
            return (ok1 and ok2), "combo_shift_q_q"
        except Exception:
            return False, "combo_emit_failed"
        finally:
            try:
                self._set_key_state(VK_SHIFT, keyup=True)
            except Exception:
                pass

    def _send_shift_rmb_hold(self, hold_sec: float) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        MOUSEEVENTF_RIGHTDOWN = 0x0008
        MOUSEEVENTF_RIGHTUP = 0x0010
        try:
            self._set_key_state(VK_SHIFT := 0xA0, keyup=False)
            time.sleep(0.01)
            user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            time.sleep(max(0.1, hold_sec))
            user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            return True, "combo_shift_rmb_hold"
        except Exception:
            return False, "combo_emit_failed"
        finally:
            try:
                self._set_key_state(VK_SHIFT, keyup=True)
            except Exception:
                pass

    def _send_shift_mouse_click(self, left: bool) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        down = 0x0002 if left else 0x0008
        up = 0x0004 if left else 0x0010
        reason = "combo_shift_lmb" if left else "combo_shift_rmb"
        try:
            self._set_key_state(VK_SHIFT := 0xA0, keyup=False)
            time.sleep(0.01)
            user32.mouse_event(down, 0, 0, 0, 0)
            time.sleep(0.03)
            user32.mouse_event(up, 0, 0, 0, 0)
            return True, reason
        except Exception:
            return False, "combo_emit_failed"
        finally:
            try:
                self._set_key_state(VK_SHIFT, keyup=True)
            except Exception:
                pass

    def _send_shift_key(self, key: str) -> tuple[bool, str]:
        vk_map = {"q": 0x51, "f": 0x46}
        vk = vk_map.get(key.lower())
        if vk is None:
            return False, "invalid_key"
        try:
            self._set_key_state(VK_SHIFT := 0xA0, keyup=False)
            time.sleep(0.01)
            ok, _ = self._tap_key(vk)
            return ok, "combo_shift_key"
        except Exception:
            return False, "combo_emit_failed"
        finally:
            try:
                self._set_key_state(VK_SHIFT, keyup=True)
            except Exception:
                pass

    def _send_hold_key(self, key: str, hold_sec: float) -> tuple[bool, str]:
        vk_map = {"q": 0x51}
        vk = vk_map.get(key.lower())
        if vk is None:
            return False, "invalid_key"
        user32 = ctypes.windll.user32
        try:
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(max(0.1, hold_sec))
            user32.keybd_event(vk, 0, 0x0002, 0)
            return True, "hold_key_emit"
        except Exception:
            return False, "combo_emit_failed"

    def _send_s_lmb(self) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        VK_S = 0x53
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        try:
            user32.keybd_event(VK_S, 0, 0, 0)
            time.sleep(0.01)
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.03)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return True, "combo_s_lmb"
        except Exception:
            return False, "combo_emit_failed"
        finally:
            try:
                user32.keybd_event(VK_S, 0, 0x0002, 0)
            except Exception:
                pass

    def _send_lmb(self) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        try:
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.03)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return True, "combo_lmb"
        except Exception:
            return False, "combo_emit_failed"

    def _tap_key(self, vk: int) -> tuple[bool, str]:
        MAPVK_VK_TO_VSC = 0
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_SCANCODE = 0x0008

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

        user32 = ctypes.windll.user32
        scan = int(user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC))

        # Prefer scan code mode for games that ignore virtual-key simulation.
        keydown = INPUT(
            type=1,
            ii=INPUTUNION(
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=scan,
                    dwFlags=KEYEVENTF_SCANCODE,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        keyup = INPUT(
            type=1,
            ii=INPUTUNION(
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=scan,
                    dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )

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

    def _set_key_state(self, vk: int, *, keyup: bool) -> bool:
        MAPVK_VK_TO_VSC = 0
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_SCANCODE = 0x0008

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

        user32 = ctypes.windll.user32
        scan = int(user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC))
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if keyup else 0)
        event = INPUT(
            type=1,
            ii=INPUTUNION(
                ki=KEYBDINPUT(
                    wVk=0,
                    wScan=scan,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
        user32.SendInput.restype = ctypes.c_uint
        sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent == 1:
            return True
        user32.keybd_event(vk, 0, 0x0002 if keyup else 0, 0)
        return False

    def _post_key_tap(self, hwnd: int, vk: int, reason: str) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        ok1 = user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
        time.sleep(0.02)
        ok2 = user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)
        return (ok1 != 0 and ok2 != 0), reason

    def _post_key_hold(self, hwnd: int, vk: int, hold_sec: float, reason: str) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        ok1 = user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
        time.sleep(max(0.1, hold_sec))
        ok2 = user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)
        return (ok1 != 0 and ok2 != 0), reason

    def _post_shift_key(self, hwnd: int, vk: int, reason: str) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        VK_SHIFT = 0x10
        ok = user32.PostMessageW(hwnd, WM_KEYDOWN, VK_SHIFT, 0)
        time.sleep(0.01)
        ok = ok and user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
        time.sleep(0.02)
        ok = ok and user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)
        ok = ok and user32.PostMessageW(hwnd, WM_KEYUP, VK_SHIFT, 0)
        return (ok != 0), reason

    def _post_shift_mouse_click(self, hwnd: int, left: bool, reason: str) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        VK_SHIFT = 0x10
        MK_SHIFT = 0x0004
        if left:
            down_msg, up_msg = 0x0201, 0x0202
        else:
            down_msg, up_msg = 0x0204, 0x0205
        ok = user32.PostMessageW(hwnd, WM_KEYDOWN, VK_SHIFT, 0)
        time.sleep(0.01)
        ok = ok and user32.PostMessageW(hwnd, down_msg, MK_SHIFT, 0)
        time.sleep(0.02)
        ok = ok and user32.PostMessageW(hwnd, up_msg, 0, 0)
        ok = ok and user32.PostMessageW(hwnd, WM_KEYUP, VK_SHIFT, 0)
        return (ok != 0), reason

    def _post_shift_mouse_hold(self, hwnd: int, right: bool, hold_sec: float, reason: str) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        VK_SHIFT = 0x10
        MK_SHIFT = 0x0004
        if right:
            down_msg, up_msg = 0x0204, 0x0205
        else:
            down_msg, up_msg = 0x0201, 0x0202
        ok = user32.PostMessageW(hwnd, WM_KEYDOWN, VK_SHIFT, 0)
        time.sleep(0.01)
        ok = ok and user32.PostMessageW(hwnd, down_msg, MK_SHIFT, 0)
        time.sleep(max(0.1, hold_sec))
        ok = ok and user32.PostMessageW(hwnd, up_msg, 0, 0)
        ok = ok and user32.PostMessageW(hwnd, WM_KEYUP, VK_SHIFT, 0)
        return (ok != 0), reason

    def _post_s_lmb(self, hwnd: int, reason: str) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        VK_S = 0x53
        WM_LBUTTONDOWN = 0x0201
        WM_LBUTTONUP = 0x0202
        ok = user32.PostMessageW(hwnd, WM_KEYDOWN, VK_S, 0)
        time.sleep(0.01)
        ok = ok and user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 0, 0)
        time.sleep(0.02)
        ok = ok and user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, 0)
        ok = ok and user32.PostMessageW(hwnd, WM_KEYUP, VK_S, 0)
        return (ok != 0), reason

    def _post_lmb(self, hwnd: int, reason: str) -> tuple[bool, str]:
        user32 = ctypes.windll.user32
        WM_LBUTTONDOWN = 0x0201
        WM_LBUTTONUP = 0x0202
        ok = user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 0, 0)
        time.sleep(0.02)
        ok = ok and user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, 0)
        return (ok != 0), reason
