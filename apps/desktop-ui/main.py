from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[2]
ORCH_SRC = ROOT / "services" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from nztbdo_orchestrator.config import list_profiles
from nztbdo_orchestrator.runtime_loop import RuntimeLoop


class DesktopUI:
    def __init__(self) -> None:
        self.profiles = list_profiles(ROOT)
        self.selected_profile = self.profiles[0] if self.profiles else "default"
        self.runtime = RuntimeLoop(profile_name=self.selected_profile)
        self.running = False
        self.paused = False
        self.panic = False

        self.root = tk.Tk()
        self.root.title("NZTBDO Control")
        self.root.geometry("680x380")
        self.root.resizable(False, False)

        self._build_layout()
        self._bind_hotkeys()
        self._schedule_tick()

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(container)
        controls.pack(fill=tk.X, pady=(0, 12))

        ttk.Button(controls, text="Start/Resume (F5)", command=self.start_resume).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls, text="Pause (F6)", command=self.pause).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls, text="Stop (F7)", command=self.stop).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls, text="Panic (F12)", command=self.panic_stop).pack(side=tk.LEFT)

        profile_row = ttk.Frame(container)
        profile_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(profile_row, text="Profile:", width=12).pack(side=tk.LEFT)
        self.profile_var = tk.StringVar(value=self.selected_profile)
        self.profile_box = ttk.Combobox(
            profile_row,
            values=self.profiles,
            textvariable=self.profile_var,
            state="readonly",
            width=20,
        )
        self.profile_box.pack(side=tk.LEFT)
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_changed)

        self.state_var = tk.StringVar(value="IDLE")
        self.action_var = tk.StringVar(value="-")
        self.reason_var = tk.StringVar(value="-")
        self.exec_var = tk.StringVar(value="-")
        self.session_var = tk.StringVar(value=self.runtime.orchestrator.session_id)
        self.profile_id_var = tk.StringVar(value=self.runtime.orchestrator.profile_id)
        self.frame_var = tk.StringVar(value="-")
        self.enemies_var = tk.StringVar(value="0")
        self.backend_var = tk.StringVar(value=self.runtime.perception.backend)
        self.window_var = tk.StringVar(value="-")
        self.process_var = tk.StringVar(value="-")
        self.guard_var = tk.StringVar(value="ok")

        info = ttk.Frame(container)
        info.pack(fill=tk.BOTH, expand=True)
        self._row(info, "State", self.state_var)
        self._row(info, "Action", self.action_var)
        self._row(info, "Reason", self.reason_var)
        self._row(info, "Execution", self.exec_var)
        self._row(info, "Session", self.session_var)
        self._row(info, "Profile", self.profile_id_var)
        self._row(info, "Frame", self.frame_var)
        self._row(info, "Enemies", self.enemies_var)
        self._row(info, "Backend", self.backend_var)
        self._row(info, "Window", self.window_var)
        self._row(info, "Process", self.process_var)
        self._row(info, "Guard", self.guard_var)

        status = ttk.Label(
            container,
            text="Hotkeys: F5 start/resume, F6 pause, F7 stop, F12 panic",
        )
        status.pack(anchor=tk.W, pady=(10, 0))

    def _row(self, parent: ttk.Frame, label: str, value: tk.StringVar) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)
        ttk.Label(frame, text=f"{label}:", width=12).pack(side=tk.LEFT)
        ttk.Label(frame, textvariable=value).pack(side=tk.LEFT)

    def _bind_hotkeys(self) -> None:
        self.root.bind("<F5>", lambda _: self.start_resume())
        self.root.bind("<F6>", lambda _: self.pause())
        self.root.bind("<F7>", lambda _: self.stop())
        self.root.bind("<F12>", lambda _: self.panic_stop())

    def start_resume(self) -> None:
        if self.panic:
            return
        self.running = True
        self.paused = False
        self.runtime.start()

    def pause(self) -> None:
        if not self.running:
            return
        self.paused = True
        self.runtime.pause()

    def stop(self) -> None:
        self.running = False
        self.paused = False
        self.panic = False
        self.runtime.stop()
        self.runtime = RuntimeLoop(profile_name=self.profile_var.get())
        self.state_var.set("IDLE")
        self.action_var.set("idle")
        self.reason_var.set("manual_stop")
        self.exec_var.set("performed=True reason=no_key_action")
        self.session_var.set(self.runtime.orchestrator.session_id)
        self.profile_id_var.set(self.runtime.orchestrator.profile_id)
        self.frame_var.set("-")
        self.enemies_var.set("0")
        self.backend_var.set(self.runtime.perception.backend)
        self.window_var.set("-")
        self.process_var.set("-")
        self.guard_var.set("ok")

    def panic_stop(self) -> None:
        self.panic = True
        self.running = False

    def _schedule_tick(self) -> None:
        self._tick()
        self.root.after(100, self._schedule_tick)

    def _tick(self) -> None:
        if not self.running and not self.panic:
            return

        if self.panic:
            state = self.runtime.panic()
            self.panic = False
        else:
            state = self.runtime.step()
            if state is None:
                return

        result = state.result
        self.state_var.set(result.state.value)
        self.action_var.set(result.action)
        self.reason_var.set(result.reason)
        self.exec_var.set(f"performed={result.execution.performed} reason={result.execution.reason}")
        self.session_var.set(self.runtime.orchestrator.session_id)
        self.profile_id_var.set(self.runtime.orchestrator.profile_id)
        self.frame_var.set(state.frame_path if state.frame_path else "-")
        self.enemies_var.set(str(state.enemies_detected))
        self.backend_var.set(self.runtime.perception.backend)
        self.window_var.set(state.window_title if state.window_title else "-")
        self.process_var.set(state.window_process if state.window_process else "-")
        self.guard_var.set("ok" if state.window_allowed else f"blocked ({state.window_reason})")

        if result.state.value == "PANIC_STOP":
            self.running = False

    def run(self) -> None:
        self.root.mainloop()

    def _on_profile_changed(self, _: object) -> None:
        if self.running:
            return
        self.selected_profile = self.profile_var.get()
        self.runtime.stop()
        self.runtime = RuntimeLoop(profile_name=self.selected_profile)
        self.state_var.set("IDLE")
        self.action_var.set("idle")
        self.reason_var.set("profile_switched")
        self.exec_var.set("performed=True reason=no_key_action")
        self.session_var.set(self.runtime.orchestrator.session_id)
        self.profile_id_var.set(self.runtime.orchestrator.profile_id)
        self.frame_var.set("-")
        self.enemies_var.set("0")
        self.backend_var.set(self.runtime.perception.backend)
        self.window_var.set("-")
        self.process_var.set("-")
        self.guard_var.set("ok")


def main() -> None:
    ui = DesktopUI()
    ui.run()


if __name__ == "__main__":
    main()
