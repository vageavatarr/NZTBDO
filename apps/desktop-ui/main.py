from __future__ import annotations

import random
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[2]
ORCH_SRC = ROOT / "services" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from nztbdo_orchestrator.main import Orchestrator, TickInput


class DesktopUI:
    def __init__(self) -> None:
        self.orchestrator = Orchestrator()
        self.running = False
        self.paused = False
        self.panic = False
        self.tick_index = 0

        self.root = tk.Tk()
        self.root.title("NZTBDO Control")
        self.root.geometry("520x300")
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

        self.state_var = tk.StringVar(value="IDLE")
        self.action_var = tk.StringVar(value="-")
        self.reason_var = tk.StringVar(value="-")
        self.exec_var = tk.StringVar(value="-")
        self.session_var = tk.StringVar(value=self.orchestrator.session_id)

        info = ttk.Frame(container)
        info.pack(fill=tk.BOTH, expand=True)
        self._row(info, "State", self.state_var)
        self._row(info, "Action", self.action_var)
        self._row(info, "Reason", self.reason_var)
        self._row(info, "Execution", self.exec_var)
        self._row(info, "Session", self.session_var)

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
        self.orchestrator.start()

    def pause(self) -> None:
        if not self.running:
            return
        self.paused = True

    def stop(self) -> None:
        self.running = False
        self.paused = False
        self.panic = False
        self.tick_index = 0
        self.orchestrator = Orchestrator()
        self.state_var.set("IDLE")
        self.action_var.set("idle")
        self.reason_var.set("manual_stop")
        self.exec_var.set("performed=True reason=no_key_action")
        self.session_var.set(self.orchestrator.session_id)

    def panic_stop(self) -> None:
        self.panic = True
        self.running = False

    def _schedule_tick(self) -> None:
        self._tick()
        self.root.after(100, self._schedule_tick)

    def _tick(self) -> None:
        if not self.running and not self.panic:
            return

        self.tick_index += 1
        tick_input = self._generate_tick()
        result = self.orchestrator.tick(tick_input)

        self.state_var.set(result.state.value)
        self.action_var.set(result.action)
        self.reason_var.set(result.reason)
        self.exec_var.set(f"performed={result.execution.performed} reason={result.execution.reason}")
        self.session_var.set(self.orchestrator.session_id)

        if result.state.value == "PANIC_STOP":
            self.running = False

    def _generate_tick(self) -> TickInput:
        if self.panic:
            self.panic = False
            return TickInput(panic=True)
        if self.paused:
            return TickInput(paused=True)

        idx = self.tick_index
        in_pull = (idx % 24) in {7, 8, 9, 10, 11, 12}
        in_cleanup = (idx % 24) == 13
        px = float(idx % 40)
        py = float((idx * 1.5) % 40)

        if not in_pull and not in_cleanup:
            return TickInput(
                pos_x=px,
                pos_y=py,
                heading_deg=0.0,
                enemy_points=[],
                engage_confidence=0.0,
                skill_cd={"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0},
            )

        pack = random.randint(2, 6)
        enemies = [(px + random.uniform(4.0, 7.0), py + random.uniform(-2.5, 2.5)) for _ in range(pack)]
        return TickInput(
            pos_x=px,
            pos_y=py,
            heading_deg=0.0,
            enemy_points=enemies,
            engage_confidence=0.78,
            combat_clear=in_cleanup,
            skill_cd={
                "1": 0.0 if idx % 3 == 0 else 2.0,
                "2": 0.0 if idx % 5 == 0 else 4.0,
                "3": 0.0,
                "4": 0.0 if idx % 9 == 0 else 9.0,
            },
        )

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ui = DesktopUI()
    ui.run()


if __name__ == "__main__":
    main()
