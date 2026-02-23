from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class EnemyPoint:
    x: float
    y: float


@dataclass(frozen=True)
class SpatialFeatures:
    enemies_total_near: int
    enemies_in_front: int
    nearest_enemy_dist: float | None


def compute_spatial_features(
    *,
    player_x: float,
    player_y: float,
    heading_deg: float,
    enemies: list[EnemyPoint],
    near_radius_m: float,
    front_cone_angle_deg: float,
    front_cone_range_m: float,
) -> SpatialFeatures:
    near_count = 0
    front_count = 0
    nearest: float | None = None

    for enemy in enemies:
        dx = enemy.x - player_x
        dy = enemy.y - player_y
        dist = math.hypot(dx, dy)
        if nearest is None or dist < nearest:
            nearest = dist

        if dist <= near_radius_m:
            near_count += 1

        if dist <= front_cone_range_m and _is_in_front(dx, dy, heading_deg, front_cone_angle_deg):
            front_count += 1

    return SpatialFeatures(
        enemies_total_near=near_count,
        enemies_in_front=front_count,
        nearest_enemy_dist=nearest,
    )


def _is_in_front(dx: float, dy: float, heading_deg: float, cone_angle_deg: float) -> bool:
    angle_to_enemy = math.degrees(math.atan2(dy, dx))
    delta = _normalize_angle(angle_to_enemy - heading_deg)
    return abs(delta) <= cone_angle_deg / 2.0


def _normalize_angle(angle_deg: float) -> float:
    value = angle_deg
    while value > 180.0:
        value -= 360.0
    while value < -180.0:
        value += 360.0
    return value
