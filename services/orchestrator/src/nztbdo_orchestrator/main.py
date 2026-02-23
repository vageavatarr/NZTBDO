from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time


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


class Orchestrator:
    def __init__(self) -> None:
        self.state = FSMState.IDLE

    def start(self) -> None:
        if self.state == FSMState.IDLE:
            self.state = FSMState.PATROL

    def tick(self, inp: TickInput) -> FSMState:
        if inp.panic:
            self.state = FSMState.PANIC_STOP
            return self.state

        if inp.paused and self.state != FSMState.PANIC_STOP:
            self.state = FSMState.PAUSED
            return self.state

        if inp.stuck and self.state not in {FSMState.PANIC_STOP, FSMState.PAUSED}:
            self.state = FSMState.RECOVERY
            return self.state

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

        return self.state


def demo() -> None:
    orchestrator = Orchestrator()
    orchestrator.start()

    timeline = [
        TickInput(),
        TickInput(enemies_total_near=3, engage_confidence=0.7),
        TickInput(enemies_total_near=2, engage_confidence=0.8),
        TickInput(enemies_total_near=1),
        TickInput(combat_clear=True),
        TickInput(),
    ]

    for idx, item in enumerate(timeline, start=1):
        state = orchestrator.tick(item)
        print(f"tick={idx} state={state.value}")
        time.sleep(0.05)


if __name__ == "__main__":
    demo()
