from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Any


@dataclass(frozen=True)
class Waypoint:
    waypoint_id: str
    x: float
    y: float
    tolerance_m: float


@dataclass(frozen=True)
class NavigationStatus:
    current_waypoint_id: str
    waypoint_index: int
    waypoint_count: int
    distance_to_waypoint: float
    reached_waypoint: bool
    stuck: bool
    action: str
    reason: str


class RouteLoopRunner:
    """Waypoint loop runner with minimal stuck detection."""

    def __init__(self, waypoints: list[Waypoint], stuck_timeout_sec: float = 6.0) -> None:
        if not waypoints:
            raise ValueError("waypoints must not be empty")
        self._waypoints = waypoints
        self._index = 0
        self._stuck_timeout_sec = stuck_timeout_sec
        self._last_progress_ts = time.monotonic()
        self._best_distance = float("inf")

    def tick(self, *, pos_x: float, pos_y: float, in_combat: bool) -> NavigationStatus:
        wp = self._waypoints[self._index]
        dist = _distance(pos_x, pos_y, wp.x, wp.y)
        reached = dist <= wp.tolerance_m

        if reached:
            self._index = (self._index + 1) % len(self._waypoints)
            self._last_progress_ts = time.monotonic()
            self._best_distance = float("inf")
            wp = self._waypoints[self._index]
            dist = _distance(pos_x, pos_y, wp.x, wp.y)
            return NavigationStatus(
                current_waypoint_id=wp.waypoint_id,
                waypoint_index=self._index,
                waypoint_count=len(self._waypoints),
                distance_to_waypoint=dist,
                reached_waypoint=True,
                stuck=False,
                action="patrol_move",
                reason="waypoint_advanced",
            )

        if dist + 0.05 < self._best_distance:
            self._best_distance = dist
            self._last_progress_ts = time.monotonic()

        stuck = (time.monotonic() - self._last_progress_ts) > self._stuck_timeout_sec
        if in_combat:
            return NavigationStatus(
                current_waypoint_id=wp.waypoint_id,
                waypoint_index=self._index,
                waypoint_count=len(self._waypoints),
                distance_to_waypoint=dist,
                reached_waypoint=False,
                stuck=False,
                action="hold_route",
                reason="combat_lock",
            )

        if stuck:
            self._last_progress_ts = time.monotonic()
            self._best_distance = float("inf")
            return NavigationStatus(
                current_waypoint_id=wp.waypoint_id,
                waypoint_index=self._index,
                waypoint_count=len(self._waypoints),
                distance_to_waypoint=dist,
                reached_waypoint=False,
                stuck=True,
                action="recover",
                reason="stuck_timeout",
            )

        return NavigationStatus(
            current_waypoint_id=wp.waypoint_id,
            waypoint_index=self._index,
            waypoint_count=len(self._waypoints),
            distance_to_waypoint=dist,
            reached_waypoint=False,
            stuck=False,
            action="patrol_move",
            reason="toward_waypoint",
        )


def load_route_runner_from_yaml(
    path: str | Path,
    *,
    stuck_timeout_sec: float = 6.0,
) -> RouteLoopRunner:
    data = _read_yaml(path)
    raw_wps = data.get("waypoints")
    if not isinstance(raw_wps, list):
        raise ValueError("route config must include waypoints list")

    waypoints: list[Waypoint] = []
    for raw in raw_wps:
        if not isinstance(raw, dict):
            continue
        waypoints.append(
            Waypoint(
                waypoint_id=str(raw.get("id", f"wp_{len(waypoints)+1:03d}")),
                x=float(raw["x"]),
                y=float(raw["y"]),
                tolerance_m=float(raw.get("tolerance_m", 2.0)),
            )
        )
    return RouteLoopRunner(waypoints=waypoints, stuck_timeout_sec=stuck_timeout_sec)


def _distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _read_yaml(path: str | Path) -> dict[str, Any]:
    import yaml  # type: ignore

    cfg_path = Path(path)
    if not cfg_path.exists():
        raise ValueError(f"route file not found: {cfg_path}")

    loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if isinstance(loaded, dict):
        return loaded
    raise ValueError("route yaml root must be object")
