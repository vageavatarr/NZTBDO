from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
import time
from typing import Any

# Bootstrap import path for local service development without packaging.
_ROOT = Path(__file__).resolve().parents[4]
_COMBAT_SRC = _ROOT / "services" / "combat" / "src"
if str(_COMBAT_SRC) not in sys.path:
    sys.path.insert(0, str(_COMBAT_SRC))

_INPUT_SRC = _ROOT / "services" / "input-control" / "src"
if str(_INPUT_SRC) not in sys.path:
    sys.path.insert(0, str(_INPUT_SRC))

from nztbdo_combat.selector import CombatSnapshot, Decision, load_selector_from_yaml
from nztbdo_input_control.executor import ActionExecutor, ExecutionResult


class FSMState(str, Enum):
    IDLE = "IDLE"
    PATROL = "PATROL"
    ENGAGE_CHECK = "ENGAGE_CHECK"
    COMBAT = "COMBAT"
    POST_COMBAT = "POST_COMBAT"
    RECOVERY = "RECOVERY"
    PAUSED = "PAUSED"
    PANIC_STOP = "PANIC_STOP"


@dataclass
class TickInput:
    enemies_total_near: int = 0
    enemies_in_front: int = 0
    engage_confidence: float = 0.0
    combat_clear: bool = False
    stuck: bool = False
    panic: bool = False
    paused: bool = False
    skill_cd: dict[str, float] | None = None


@dataclass
class TickResult:
    state: FSMState
    action: str
    reason: str
    execution: ExecutionResult


class Orchestrator:
    def __init__(self) -> None:
        self.state = FSMState.IDLE
        skills_config = _ROOT / "shared" / "config" / "skills.yaml"
        self._combat_selector = load_selector_from_yaml(skills_config)
        self._executor = ActionExecutor(max_hz=self._read_action_rate_limit(), dry_run=True)

    def start(self) -> None:
        if self.state == FSMState.IDLE:
            self.state = FSMState.PATROL

    def tick(self, inp: TickInput) -> TickResult:
        cooldowns = inp.skill_cd or {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0}

        if inp.panic:
            self.state = FSMState.PANIC_STOP
            action = "panic_stop"
            return TickResult(
                state=self.state,
                action=action,
                reason="panic_hotkey",
                execution=self._executor.execute(action),
            )

        if inp.paused and self.state != FSMState.PANIC_STOP:
            self.state = FSMState.PAUSED
            action = "pause"
            return TickResult(
                state=self.state,
                action=action,
                reason="pause_hotkey",
                execution=self._executor.execute(action),
            )

        if inp.stuck and self.state not in {FSMState.PANIC_STOP, FSMState.PAUSED}:
            self.state = FSMState.RECOVERY
            action = "recover"
            return TickResult(
                state=self.state,
                action=action,
                reason="stuck_detected",
                execution=self._executor.execute(action),
            )

        if self.state == FSMState.PATROL:
            if inp.enemies_total_near > 0:
                self.state = FSMState.ENGAGE_CHECK

        elif self.state == FSMState.ENGAGE_CHECK:
            if inp.engage_confidence >= 0.65:
                self.state = FSMState.COMBAT
            else:
                self.state = FSMState.PATROL

        elif self.state == FSMState.COMBAT:
            if inp.combat_clear:
                self.state = FSMState.POST_COMBAT

        elif self.state == FSMState.POST_COMBAT:
            self.state = FSMState.PATROL

        elif self.state == FSMState.RECOVERY:
            self.state = FSMState.PATROL

        if self.state == FSMState.COMBAT:
            decision = self._combat_selector.decide(
                CombatSnapshot(
                    enemies_total_near=inp.enemies_total_near,
                    enemies_in_front=inp.enemies_in_front,
                    skill_cd=cooldowns,
                )
            )
            execution = self._executor.execute(decision.action)
            return TickResult(
                state=self.state,
                action=decision.action,
                reason=decision.reason,
                execution=execution,
            )

        decision = self._default_action_for_state(self.state)
        execution = self._executor.execute(decision.action)
        return TickResult(
            state=self.state,
            action=decision.action,
            reason=decision.reason,
            execution=execution,
        )

    @staticmethod
    def _default_action_for_state(state: FSMState) -> Decision:
        if state == FSMState.IDLE:
            return Decision(action="idle", reason="await_start")
        if state == FSMState.PATROL:
            return Decision(action="patrol_move", reason="route_follow")
        if state == FSMState.ENGAGE_CHECK:
            return Decision(action="face_target", reason="engage_validation")
        if state == FSMState.POST_COMBAT:
            return Decision(action="resume_route", reason="area_clear")
        if state == FSMState.RECOVERY:
            return Decision(action="recover", reason="state_recovery")
        if state == FSMState.PAUSED:
            return Decision(action="pause", reason="paused")
        if state == FSMState.PANIC_STOP:
            return Decision(action="panic_stop", reason="panic")
        return Decision(action="idle", reason="fallback")

    @staticmethod
    def _read_action_rate_limit() -> int:
        cfg = _read_yaml(_ROOT / "shared" / "config" / "thresholds.yaml")
        combat_cfg = cfg.get("combat")
        if not isinstance(combat_cfg, dict):
            return 8
        value = combat_cfg.get("action_rate_limit_hz")
        if isinstance(value, int) and value > 0:
            return value
        return 8


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}

    if not path.exists():
        return {}

    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    try:
        loaded = yaml.safe_load(content)
    except Exception:
        return {}

    if isinstance(loaded, dict):
        return loaded
    return {}


def demo() -> None:
    orchestrator = Orchestrator()
    orchestrator.start()

    timeline = [
        TickInput(),
        TickInput(enemies_total_near=3, engage_confidence=0.7),
        TickInput(
            enemies_total_near=5,
            enemies_in_front=4,
            engage_confidence=0.8,
            skill_cd={"1": 0.0, "2": 0.0, "3": 0.0, "4": 7.0},
        ),
        TickInput(
            enemies_total_near=2,
            enemies_in_front=0,
            skill_cd={"1": 5.0, "2": 7.0, "3": 0.0, "4": 6.0},
        ),
        TickInput(combat_clear=True),
        TickInput(),
    ]

    for idx, item in enumerate(timeline, start=1):
        result = orchestrator.tick(item)
        print(
            f"tick={idx} state={result.state.value} "
            f"action={result.action} reason={result.reason} "
            f"performed={result.execution.performed} "
            f"exec_reason={result.execution.reason}"
        )
        time.sleep(0.05)


if __name__ == "__main__":
    demo()
