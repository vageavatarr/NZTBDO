from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import time

from nztbdo_orchestrator.main import Orchestrator, TickInput, TickResult

_ROOT = Path(__file__).resolve().parents[4]
_CAPTURE_SRC = _ROOT / "services" / "capture" / "src"
if str(_CAPTURE_SRC) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_SRC))

_PERCEPTION_SRC = _ROOT / "services" / "perception" / "src"
if str(_PERCEPTION_SRC) not in sys.path:
    sys.path.insert(0, str(_PERCEPTION_SRC))

from nztbdo_capture.input_recorder import InputTelemetryRecorder
from nztbdo_capture.screen_capture import PrimaryMonitorCapture
from nztbdo_perception.runtime_adapter import RuntimePerceptionAdapter


@dataclass(frozen=True)
class RuntimeState:
    tick_index: int
    frame_path: str
    enemies_detected: int
    result: TickResult


class RuntimeLoop:
    def __init__(self, profile_name: str = "default") -> None:
        self.orchestrator = Orchestrator(profile_name=profile_name)
        self.perception = RuntimePerceptionAdapter()
        self.capture = PrimaryMonitorCapture()
        self.tick_index = 0
        self._running = False
        self._paused = False
        self._had_enemies = False
        self._last_runtime_state: RuntimeState | None = None

        self._raw_session_dir = _ROOT / "data" / "raw" / self.orchestrator.session_id
        self._frames_dir = self._raw_session_dir / "frames"
        self._telemetry = InputTelemetryRecorder(str(self._raw_session_dir), chunk_size=400)

    def start(self) -> None:
        self._running = True
        self._paused = False
        self.orchestrator.start()

    def pause(self) -> None:
        if self._running:
            self._paused = True

    def stop(self) -> None:
        self._running = False
        self._paused = False
        self.orchestrator.stop()
        self.capture.close()
        self._telemetry.close()

    def panic(self) -> RuntimeState:
        result = self.orchestrator.tick(TickInput(panic=True))
        state = RuntimeState(
            tick_index=self.tick_index,
            frame_path="",
            enemies_detected=0,
            result=result,
        )
        self._last_runtime_state = state
        self.stop()
        return state

    def step(self) -> RuntimeState | None:
        if not self._running:
            return None

        self.tick_index += 1
        if self._paused:
            result = self.orchestrator.tick(TickInput(paused=True))
            state = RuntimeState(
                tick_index=self.tick_index,
                frame_path="",
                enemies_detected=0,
                result=result,
            )
            self._last_runtime_state = state
            return state

        px = float(self.tick_index % 40)
        py = float((self.tick_index * 1.75) % 40)

        frame = self.capture.capture_to_png(
            frames_dir=self._frames_dir,
            prefix="frame",
            index=self.tick_index,
        )
        self._telemetry.record_frame_meta(
            frame_id=frame.frame_id,
            width=frame.width,
            height=frame.height,
            path=frame.path,
        )

        enemies = self.perception.detect_enemy_points(
            frame_path=frame.path,
            player_x=px,
            player_y=py,
        )
        has_enemies = len(enemies) > 0
        combat_clear = self._had_enemies and (not has_enemies)
        self._had_enemies = has_enemies

        tick_input = TickInput(
            pos_x=px,
            pos_y=py,
            heading_deg=0.0,
            enemy_points=enemies,
            engage_confidence=0.78 if has_enemies else 0.0,
            combat_clear=combat_clear,
            skill_cd={
                "1": 0.0 if self.tick_index % 3 == 0 else 2.0,
                "2": 0.0 if self.tick_index % 5 == 0 else 4.0,
                "3": 0.0,
                "4": 0.0 if self.tick_index % 9 == 0 else 9.0,
            },
        )
        result = self.orchestrator.tick(tick_input)
        self._telemetry.record_window(
            title="Unknown",
            process="unknown.exe",
            rect=self.capture.primary_monitor,
        )

        state = RuntimeState(
            tick_index=self.tick_index,
            frame_path=frame.path,
            enemies_detected=len(enemies),
            result=result,
        )
        self._last_runtime_state = state
        return state

    @property
    def last_runtime_state(self) -> RuntimeState | None:
        return self._last_runtime_state


def main() -> None:
    loop = RuntimeLoop(profile_name="default")
    loop.start()
    started = time.time()
    for _ in range(60):
        state = loop.step()
        if state is None:
            break
        print(
            f"tick={state.tick_index} state={state.result.state.value} "
            f"action={state.result.action} enemies={state.enemies_detected}"
        )
        time.sleep(0.05)
    elapsed = time.time() - started
    loop.stop()
    print(f"runtime_elapsed_sec={elapsed:.2f} session={loop.orchestrator.session_id}")


if __name__ == "__main__":
    main()
