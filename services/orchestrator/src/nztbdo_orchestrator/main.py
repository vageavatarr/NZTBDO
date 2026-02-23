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

_NAV_SRC = _ROOT / "services" / "navigation" / "src"
if str(_NAV_SRC) not in sys.path:
    sys.path.insert(0, str(_NAV_SRC))

_PERCEPTION_SRC = _ROOT / "services" / "perception" / "src"
if str(_PERCEPTION_SRC) not in sys.path:
    sys.path.insert(0, str(_PERCEPTION_SRC))

from nztbdo_combat.selector import CombatSnapshot, Decision, load_selector_from_yaml
_CAPTURE_SRC = _ROOT / "services" / "capture" / "src"
if str(_CAPTURE_SRC) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_SRC))

from nztbdo_capture.session_logger import SessionLogger
from nztbdo_input_control.executor import ActionExecutor, ExecutionResult
from nztbdo_navigation.route_runner import NavigationStatus, load_route_runner_from_yaml
from nztbdo_perception.spatial import EnemyPoint, compute_spatial_features
from nztbdo_orchestrator.config import load_profile_config


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
    pos_x: float = 0.0
    pos_y: float = 0.0
    heading_deg: float = 0.0
    enemy_points: list[tuple[float, float]] | None = None


@dataclass
class TickResult:
    state: FSMState
    action: str
    reason: str
    execution: ExecutionResult
    navigation: NavigationStatus | None = None


class Orchestrator:
    def __init__(self, profile_name: str = "default") -> None:
        self._cfg = load_profile_config(_ROOT, profile_name)
        self.state = FSMState.IDLE
        self._combat_selector = load_selector_from_yaml(self._cfg.skills_path)
        input_cfg = self._read_input_control_cfg()
        self._executor = ActionExecutor(
            max_hz=self._read_action_rate_limit(),
            dry_run=input_cfg["dry_run"],
            allowed_window_substrings=input_cfg["allowed_window_titles"],
            allowed_process_names=input_cfg["allowed_process_names"],
            bind_to_process=input_cfg["bind_to_process"],
            allow_background_input=input_cfg["allow_background_input"],
        )
        self._logger = SessionLogger(_ROOT / "data" / "logs")
        self._nav_runner = load_route_runner_from_yaml(
            self._cfg.route_path,
            stuck_timeout_sec=float(self._read_stuck_timeout_sec()),
        )
        self._perception_cfg = self._read_perception_cfg()

    @property
    def session_id(self) -> str:
        return self._logger.session_id

    @property
    def profile_id(self) -> str:
        return self._cfg.profile_id

    @property
    def events_path(self) -> Path:
        return self._logger.events_path

    @property
    def thresholds_path(self) -> Path:
        return self._cfg.thresholds_path

    def write_runtime_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = dict(payload)
        event["event_type"] = event_type
        self._logger.write_event(event)

    def start(self) -> None:
        if self.state == FSMState.IDLE:
            self.state = FSMState.PATROL

    def stop(self) -> None:
        self.state = FSMState.IDLE

    def tick(self, inp: TickInput) -> TickResult:
        cooldowns = inp.skill_cd or {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0}
        enemies_total_near, enemies_in_front = self._resolve_enemy_features(inp)

        if inp.panic:
            self.state = FSMState.PANIC_STOP
            action = "panic_stop"
            result = TickResult(
                state=self.state,
                action=action,
                reason="panic_hotkey",
                execution=self._executor.execute(action),
                navigation=None,
            )
            self._log_tick(inp, result)
            return result

        if inp.paused and self.state != FSMState.PANIC_STOP:
            self.state = FSMState.PAUSED
            action = "pause"
            result = TickResult(
                state=self.state,
                action=action,
                reason="pause_hotkey",
                execution=self._executor.execute(action),
                navigation=None,
            )
            self._log_tick(inp, result)
            return result

        nav = self._nav_runner.tick(
            pos_x=inp.pos_x,
            pos_y=inp.pos_y,
            in_combat=self.state == FSMState.COMBAT,
        )

        if nav.stuck and self.state not in {FSMState.PANIC_STOP, FSMState.PAUSED, FSMState.COMBAT}:
            self.state = FSMState.RECOVERY

        if inp.stuck and self.state not in {FSMState.PANIC_STOP, FSMState.PAUSED}:
            self.state = FSMState.RECOVERY
            action = "recover"
            result = TickResult(
                state=self.state,
                action=action,
                reason="stuck_detected",
                execution=self._executor.execute(action),
                navigation=nav,
            )
            self._log_tick(inp, result)
            return result

        if self.state == FSMState.PATROL:
            if enemies_total_near > 0:
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
                    enemies_total_near=enemies_total_near,
                    enemies_in_front=enemies_in_front,
                    skill_cd=cooldowns,
                )
            )
            execution = self._executor.execute(decision.action)
            result = TickResult(
                state=self.state,
                action=decision.action,
                reason=decision.reason,
                execution=execution,
                navigation=nav,
            )
            self._log_tick(inp, result)
            return result

        decision = self._default_action_for_state(self.state, nav)
        execution = self._executor.execute(decision.action)
        result = TickResult(
            state=self.state,
            action=decision.action,
            reason=decision.reason,
            execution=execution,
            navigation=nav,
        )
        self._log_tick(inp, result)
        return result

    @staticmethod
    def _default_action_for_state(state: FSMState, nav: NavigationStatus | None) -> Decision:
        if state == FSMState.IDLE:
            return Decision(action="idle", reason="await_start")
        if state == FSMState.PATROL:
            if nav is not None:
                return Decision(action=nav.action, reason=nav.reason)
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

    def _read_action_rate_limit(self) -> int:
        cfg = _read_yaml(self._cfg.thresholds_path)
        combat_cfg = cfg.get("combat")
        if not isinstance(combat_cfg, dict):
            return 8
        value = combat_cfg.get("action_rate_limit_hz")
        if isinstance(value, int) and value > 0:
            return value
        return 8

    def _read_stuck_timeout_sec(self) -> float:
        cfg = _read_yaml(self._cfg.thresholds_path)
        nav_cfg = cfg.get("navigation")
        if not isinstance(nav_cfg, dict):
            return 6.0
        value = nav_cfg.get("stuck_timeout_sec")
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
        return 6.0

    def _read_perception_cfg(self) -> dict[str, float]:
        cfg = _read_yaml(self._cfg.thresholds_path)
        perception_cfg = cfg.get("perception")
        if not isinstance(perception_cfg, dict):
            return {
                "near_radius_m": 8.0,
                "front_cone_angle_deg": 90.0,
                "front_cone_range_m": 7.0,
            }
        near = perception_cfg.get("near_radius_m", 8.0)
        angle = perception_cfg.get("front_cone_angle_deg", 90.0)
        rng = perception_cfg.get("front_cone_range_m", 7.0)
        return {
            "near_radius_m": float(near),
            "front_cone_angle_deg": float(angle),
            "front_cone_range_m": float(rng),
        }

    def _read_input_control_cfg(self) -> dict[str, Any]:
        cfg = _read_yaml(self._cfg.thresholds_path)
        input_cfg = cfg.get("input_control")
        if not isinstance(input_cfg, dict):
            return {
                "dry_run": True,
                "allowed_window_titles": [],
                "allowed_process_names": [],
                "bind_to_process": False,
                "allow_background_input": False,
            }

        dry_run = input_cfg.get("dry_run", True)
        titles = input_cfg.get("allowed_window_titles", [])
        processes = input_cfg.get("allowed_process_names", [])
        if not isinstance(titles, list):
            titles = []
        if not isinstance(processes, list):
            processes = []
        titles_clean = [str(item) for item in titles if str(item).strip()]
        processes_clean = [str(item) for item in processes if str(item).strip()]
        return {
            "dry_run": bool(dry_run),
            "allowed_window_titles": titles_clean,
            "allowed_process_names": processes_clean,
            "bind_to_process": bool(input_cfg.get("bind_to_process", False)),
            "allow_background_input": bool(input_cfg.get("allow_background_input", False)),
        }

    def _resolve_enemy_features(self, inp: TickInput) -> tuple[int, int]:
        if not inp.enemy_points:
            return inp.enemies_total_near, inp.enemies_in_front

        enemies = [EnemyPoint(x=item[0], y=item[1]) for item in inp.enemy_points]
        features = compute_spatial_features(
            player_x=inp.pos_x,
            player_y=inp.pos_y,
            heading_deg=inp.heading_deg,
            enemies=enemies,
            near_radius_m=self._perception_cfg["near_radius_m"],
            front_cone_angle_deg=self._perception_cfg["front_cone_angle_deg"],
            front_cone_range_m=self._perception_cfg["front_cone_range_m"],
        )
        return features.enemies_total_near, features.enemies_in_front

    def _log_tick(self, inp: TickInput, result: TickResult) -> None:
        self._logger.write_tick(
            timestamp_ms=int(time.time() * 1000),
            fsm_state=result.state.value,
            tick_input=inp,
            action=result.action,
            reason=result.reason,
            execution=result.execution,
            navigation=result.navigation,
        )


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
        TickInput(pos_x=0.0, pos_y=0.0),
        TickInput(
            engage_confidence=0.7,
            pos_x=2.0,
            pos_y=1.0,
            heading_deg=0.0,
            enemy_points=[(5.0, 1.2), (6.3, 0.5), (4.8, 2.5)],
        ),
        TickInput(
            engage_confidence=0.8,
            skill_cd={
                "aoe_around_shift_q": 0.0,
                "aoe_followup_hold_q_4s": 0.0,
                "front_hold_shift_rmb": 0.0,
                "front_shift_lmb": 0.0,
                "front_long_shift_f": 7.0,
                "finisher_s_lmb": 0.0,
                "basic_lmb": 0.0,
            },
            pos_x=3.0,
            pos_y=1.0,
            heading_deg=0.0,
            enemy_points=[(6.0, 1.0), (6.5, 2.0), (7.0, 0.8), (7.2, 1.2), (3.1, 8.0)],
        ),
        TickInput(
            skill_cd={
                "aoe_around_shift_q": 5.0,
                "aoe_followup_hold_q_4s": 6.0,
                "front_hold_shift_rmb": 7.0,
                "front_shift_lmb": 0.0,
                "front_long_shift_f": 6.0,
                "finisher_s_lmb": 0.0,
                "basic_lmb": 0.0,
            },
            pos_x=3.0,
            pos_y=1.0,
            heading_deg=0.0,
            enemy_points=[(2.5, 4.5), (2.0, 4.8)],
        ),
        TickInput(combat_clear=True, pos_x=34.0, pos_y=4.2),
        TickInput(pos_x=35.1, pos_y=4.1),
    ]

    for idx, item in enumerate(timeline, start=1):
        result = orchestrator.tick(item)
        wp = result.navigation.current_waypoint_id if result.navigation else "-"
        print(
            f"tick={idx} state={result.state.value} "
            f"action={result.action} reason={result.reason} "
            f"performed={result.execution.performed} "
            f"exec_reason={result.execution.reason} wp={wp}"
        )
        time.sleep(0.05)


if __name__ == "__main__":
    demo()
