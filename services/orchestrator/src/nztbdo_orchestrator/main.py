from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
import time

# Bootstrap import path for local service development without packaging.
_ROOT = Path(__file__).resolve().parents[4]
_COMBAT_SRC = _ROOT / "services" / "combat" / "src"
if str(_COMBAT_SRC) not in sys.path:
    sys.path.insert(0, str(_COMBAT_SRC))

from nztbdo_combat.selector import CombatSnapshot, Decision, default_selector


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


class Orchestrator:
    def __init__(self) -> None:
        self.state = FSMState.IDLE
        self._combat_selector = default_selector()

    def start(self) -> None:
        if self.state == FSMState.IDLE:
            self.state = FSMState.PATROL

    def tick(self, inp: TickInput) -> TickResult:
        cooldowns = inp.skill_cd or {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0}

        if inp.panic:
            self.state = FSMState.PANIC_STOP
            return TickResult(state=self.state, action="panic_stop", reason="panic_hotkey")

        if inp.paused and self.state != FSMState.PANIC_STOP:
            self.state = FSMState.PAUSED
            return TickResult(state=self.state, action="pause", reason="pause_hotkey")

        if inp.stuck and self.state not in {FSMState.PANIC_STOP, FSMState.PAUSED}:
            self.state = FSMState.RECOVERY
            return TickResult(state=self.state, action="recover", reason="stuck_detected")

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
            return TickResult(state=self.state, action=decision.action, reason=decision.reason)

        decision = self._default_action_for_state(self.state)
        return TickResult(state=self.state, action=decision.action, reason=decision.reason)

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
            f"action={result.action} reason={result.reason}"
        )
        time.sleep(0.05)


if __name__ == "__main__":
    demo()
