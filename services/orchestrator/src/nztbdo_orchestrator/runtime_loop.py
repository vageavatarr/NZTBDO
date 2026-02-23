from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from pathlib import Path
import sys
import time
from typing import Any

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
from nztbdo_orchestrator.window_guard import WindowCheck, WindowGuard


@dataclass(frozen=True)
class RuntimeState:
    tick_index: int
    frame_path: str
    enemies_detected: int
    result: TickResult
    window_title: str
    window_process: str
    window_allowed: bool
    window_reason: str
    track_ids: list[int]


class RuntimeLoop:
    def __init__(self, profile_name: str = "default") -> None:
        self.orchestrator = Orchestrator(profile_name=profile_name)
        self._runtime_cfg = self._read_runtime_perception_cfg()
        self.perception = RuntimePerceptionAdapter(
            backend=str(self._runtime_cfg["detector_backend"]),
            model_path=str(self._runtime_cfg["model_path"]),
            confidence_min=float(self._runtime_cfg["confidence_min"]),
            pixel_to_meter=float(self._runtime_cfg["pixel_to_meter"]),
            max_targets=int(self._runtime_cfg["max_targets"]),
            enemy_class_ids=list(self._runtime_cfg["enemy_class_ids"]),
        )
        self.capture = PrimaryMonitorCapture()
        input_cfg = self._read_input_control_cfg()
        self.window_guard = WindowGuard(
            allowed_titles=list(input_cfg["allowed_window_titles"]),
            allowed_processes=list(input_cfg["allowed_process_names"]),
        )
        self.tick_index = 0
        self._running = False
        self._paused = False
        self._paused_by_guard = False
        self._had_enemies = False
        self._last_runtime_state: RuntimeState | None = None

        self._raw_session_dir = _ROOT / "data" / "raw" / self.orchestrator.session_id
        self._frames_dir = self._raw_session_dir / "frames"
        self._telemetry = InputTelemetryRecorder(str(self._raw_session_dir), chunk_size=400)

    def start(self) -> None:
        self._running = True
        self._paused = False
        self._paused_by_guard = False
        self.orchestrator.start()

    def pause(self) -> None:
        if self._running:
            self._paused = True
            self._paused_by_guard = False

    def stop(self) -> None:
        self._running = False
        self._paused = False
        self._paused_by_guard = False
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
            window_title="",
            window_process="",
            window_allowed=False,
            window_reason="panic",
            track_ids=[],
        )
        self._last_runtime_state = state
        self.stop()
        return state

    def step(self) -> RuntimeState | None:
        if not self._running:
            return None

        self.tick_index += 1
        window_check = self.window_guard.check()
        if self._paused:
            # Auto-resume only when pause was caused by guard and target window is back in focus.
            if self._paused_by_guard and window_check.allowed:
                self._paused = False
                self._paused_by_guard = False
            else:
                result = self.orchestrator.tick(TickInput(paused=True))
                self._telemetry.record_window(
                    title=window_check.title or "Unknown",
                    process=window_check.process_name or "unknown.exe",
                    rect=self.capture.primary_monitor,
                )
                state = RuntimeState(
                    tick_index=self.tick_index,
                    frame_path="",
                    enemies_detected=0,
                    result=result,
                    window_title=window_check.title,
                    window_process=window_check.process_name,
                    window_allowed=window_check.allowed,
                    window_reason="guard_pause" if self._paused_by_guard else "paused",
                    track_ids=[],
                )
                self._last_runtime_state = state
                return state

        if self._paused:
            result = self.orchestrator.tick(TickInput(paused=True))
            self._telemetry.record_window(
                title=window_check.title or "Unknown",
                process=window_check.process_name or "unknown.exe",
                rect=self.capture.primary_monitor,
            )
            state = RuntimeState(
                tick_index=self.tick_index,
                frame_path="",
                enemies_detected=0,
                result=result,
                window_title=window_check.title,
                window_process=window_check.process_name,
                window_allowed=window_check.allowed,
                window_reason="guard_pause" if self._paused_by_guard else "paused",
                track_ids=[],
            )
            self._last_runtime_state = state
            return state

        if not window_check.allowed:
            self._paused = True
            self._paused_by_guard = True
            result = self.orchestrator.tick(TickInput(paused=True))
            self._telemetry.record_window(
                title=window_check.title or "Unknown",
                process=window_check.process_name or "unknown.exe",
                rect=self.capture.primary_monitor,
            )
            state = RuntimeState(
                tick_index=self.tick_index,
                frame_path="",
                enemies_detected=0,
                result=result,
                window_title=window_check.title,
                window_process=window_check.process_name,
                window_allowed=False,
                window_reason=window_check.reason,
                track_ids=[],
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
            title=window_check.title or "Unknown",
            process=window_check.process_name or "unknown.exe",
            rect=self.capture.primary_monitor,
        )

        state = RuntimeState(
            tick_index=self.tick_index,
            frame_path=frame.path,
            enemies_detected=len(enemies),
            result=result,
            window_title=window_check.title,
            window_process=window_check.process_name,
            window_allowed=window_check.allowed,
            window_reason=window_check.reason,
            track_ids=self.perception.last_track_ids,
        )
        self._last_runtime_state = state
        return state

    @property
    def last_runtime_state(self) -> RuntimeState | None:
        return self._last_runtime_state

    def _read_runtime_perception_cfg(self) -> dict[str, Any]:
        cfg = _read_yaml(self.orchestrator.thresholds_path)
        perception_cfg = cfg.get("perception")
        if not isinstance(perception_cfg, dict):
            perception_cfg = {}
        runtime_cfg = perception_cfg.get("runtime")
        if not isinstance(runtime_cfg, dict):
            runtime_cfg = {}

        enemy_ids = runtime_cfg.get("enemy_class_ids", [])
        if not isinstance(enemy_ids, list):
            enemy_ids = []
        cleaned_enemy_ids = [int(item) for item in enemy_ids if isinstance(item, (int, float))]

        model_path = str(runtime_cfg.get("model_path", ""))
        model_abs = str((_ROOT / model_path).resolve()) if model_path else ""

        return {
            "detector_backend": runtime_cfg.get("detector_backend", "auto"),
            "model_path": model_abs,
            "confidence_min": runtime_cfg.get("confidence_min", 0.45),
            "pixel_to_meter": runtime_cfg.get("pixel_to_meter", 0.01),
            "max_targets": runtime_cfg.get("max_targets", 8),
            "enemy_class_ids": cleaned_enemy_ids,
        }

    def _read_input_control_cfg(self) -> dict[str, Any]:
        cfg = _read_yaml(self.orchestrator.thresholds_path)
        input_cfg = cfg.get("input_control")
        if not isinstance(input_cfg, dict):
            return {"allowed_window_titles": [], "allowed_process_names": []}

        titles = input_cfg.get("allowed_window_titles", [])
        processes = input_cfg.get("allowed_process_names", [])
        if not isinstance(titles, list):
            titles = []
        if not isinstance(processes, list):
            processes = []
        return {
            "allowed_window_titles": [str(v) for v in titles if str(v).strip()],
            "allowed_process_names": [str(v) for v in processes if str(v).strip()],
        }


def run(
    profile_name: str,
    ticks: int,
    tick_sleep: float,
    verbose: bool = True,
    start_delay: float = 0.0,
) -> dict[str, Any]:
    loop = RuntimeLoop(profile_name=profile_name)
    loop.start()
    if start_delay > 0:
        time.sleep(start_delay)
    states = Counter()
    actions = Counter()
    execution_reasons = Counter()
    total_enemies = 0
    total_tracks = 0
    raw_detections_total = 0
    confidence_sum = 0.0
    confidence_count = 0
    confidence_min = 1.0
    confidence_max = 0.0
    class_counts: Counter[int] = Counter()

    started = time.time()
    for _ in range(ticks):
        state = loop.step()
        if state is None:
            break
        states[state.result.state.value] += 1
        actions[state.result.action] += 1
        execution_reasons[state.result.execution.reason] += 1
        total_enemies += state.enemies_detected
        total_tracks += len(state.track_ids)
        confidences = loop.perception.last_confidences
        classes = loop.perception.last_class_ids
        raw_detections_total += len(confidences)
        for conf in confidences:
            confidence_sum += conf
            confidence_count += 1
            if conf < confidence_min:
                confidence_min = conf
            if conf > confidence_max:
                confidence_max = conf
        for cls in classes:
            class_counts[int(cls)] += 1
        if not state.window_allowed:
            execution_reasons["window_guard_blocked"] += 1

        if verbose:
            print(
                f"tick={state.tick_index} state={state.result.state.value} "
                f"action={state.result.action} enemies={state.enemies_detected} "
                f"window_allowed={state.window_allowed}"
            )
        time.sleep(tick_sleep)

    elapsed = max(time.time() - started, 0.001)
    loop.stop()
    summary = {
        "profile": profile_name,
        "session_id": loop.orchestrator.session_id,
        "events_path": str(loop.orchestrator.events_path),
        "ticks": ticks,
        "elapsed_sec": round(elapsed, 3),
        "tps": round(ticks / elapsed, 2),
        "states": dict(states),
        "actions": dict(actions),
        "execution_reasons": dict(execution_reasons),
        "perception_backend": loop.perception.backend,
        "perception_requested_backend": loop.perception.requested_backend,
        "perception_model_path": loop.perception.model_path,
        "perception_model_exists": loop.perception.model_exists,
        "perception_ultralytics_available": loop.perception.ultralytics_available,
        "perception_init_reason": loop.perception.init_reason,
        "avg_enemies_detected_per_tick": round(total_enemies / max(ticks, 1), 3),
        "avg_tracks_per_tick": round(total_tracks / max(ticks, 1), 3),
        "detection_analytics": {
            "raw_detections_total": raw_detections_total,
            "avg_confidence": round(confidence_sum / max(confidence_count, 1), 4),
            "min_confidence": round(confidence_min if confidence_count else 0.0, 4),
            "max_confidence": round(confidence_max if confidence_count else 0.0, 4),
            "class_counts": {str(k): int(v) for k, v in class_counts.items()},
        },
        "window_guard_constraints": {
            "titles": loop.window_guard.allowed_titles,
            "processes": loop.window_guard.allowed_processes,
        },
    }
    summary_path = Path(loop.orchestrator.events_path).with_name("runtime_summary.json")
    summary_path.write_text(str(_to_pretty_json(summary)), encoding="utf-8")
    summary["runtime_summary_path"] = str(summary_path)
    return summary


def main() -> None:
    summary = run(profile_name="default", ticks=60, tick_sleep=0.05, verbose=True)
    print(_to_compact_json(summary))


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _to_pretty_json(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, ensure_ascii=True, indent=2)


def _to_compact_json(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, ensure_ascii=True)


if __name__ == "__main__":
    main()
