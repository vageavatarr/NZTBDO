from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Skill:
    skill_id: str
    key: str
    kind: str
    priority: int
    min_targets: int
    max_targets: int = 999


@dataclass(frozen=True)
class CombatSnapshot:
    enemies_total_near: int
    enemies_in_front: int
    skill_cd: dict[str, float]


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


class CombatSelector:
    """Rule-based skill selection with cooldown and geometry-aware priority."""

    def __init__(self, skills: list[Skill]) -> None:
        self._skills = sorted(skills, key=lambda s: s.priority, reverse=True)

    def decide(self, snapshot: CombatSnapshot) -> Decision:
        ranked = self.ranked_actions(snapshot)
        if ranked:
            return ranked[0]
        return Decision(action="patrol_move", reason="no_enemies")

    def ranked_actions(self, snapshot: CombatSnapshot) -> list[Decision]:
        ranked: list[Decision] = []
        front_ready = self._ready_candidates(
            kinds={"cone", "line"},
            targets=snapshot.enemies_in_front,
            cooldowns=snapshot.skill_cd,
        )
        if front_ready:
            ranked.extend(Decision(action=f"press_{skill.key}", reason="front_aoe") for skill in front_ready)

        around_ready = self._ready_candidates(
            kinds={"circle"},
            targets=snapshot.enemies_total_near,
            cooldowns=snapshot.skill_cd,
        )
        if around_ready:
            ranked.extend(Decision(action=f"press_{skill.key}", reason="around_aoe") for skill in around_ready)

        single_ready = self._ready_candidates(
            kinds={"single"},
            targets=snapshot.enemies_total_near,
            cooldowns=snapshot.skill_cd,
        )
        if single_ready:
            ranked.extend(Decision(action=f"press_{skill.key}", reason="single_target") for skill in single_ready)

        if ranked:
            return ranked

        if snapshot.enemies_total_near > 0 and snapshot.enemies_in_front == 0:
            return [Decision(action="reposition", reason="no_front_targets")]

        if snapshot.enemies_total_near > 0:
            return [Decision(action="wait_cd", reason="cooldown_wait")]

        return [Decision(action="patrol_move", reason="no_enemies")]

    def _ready_candidates(
        self,
        kinds: set[str],
        targets: int,
        cooldowns: dict[str, float],
    ) -> list[Skill]:
        ready: list[Skill] = []
        for skill in self._skills:
            if skill.kind not in kinds:
                continue
            if targets < skill.min_targets:
                continue
            if targets > skill.max_targets:
                continue
            # Prefer cooldown by stable skill id; fallback to key for older configs.
            if cooldowns.get(skill.skill_id, cooldowns.get(skill.key, 999.0)) > 0:
                continue
            ready.append(skill)
        return ready


def default_selector() -> CombatSelector:
    return CombatSelector(
        skills=[
            Skill(
                skill_id="slash_front",
                key="1",
                kind="cone",
                priority=90,
                min_targets=3,
                max_targets=999,
            ),
            Skill(
                skill_id="whirlwind",
                key="2",
                kind="circle",
                priority=80,
                min_targets=4,
                max_targets=999,
            ),
            Skill(
                skill_id="strike",
                key="3",
                kind="single",
                priority=70,
                min_targets=1,
                max_targets=999,
            ),
            Skill(
                skill_id="execute",
                key="4",
                kind="single",
                priority=60,
                min_targets=1,
                max_targets=999,
            ),
        ]
    )


def load_selector_from_yaml(path: str | Path) -> CombatSelector:
    """Load selector skills from YAML config. Falls back to defaults on errors."""
    data = _read_yaml(path)
    if not data:
        return default_selector()

    raw_skills = data.get("skills")
    if not isinstance(raw_skills, list):
        return default_selector()

    skills: list[Skill] = []
    for item in raw_skills:
        if not isinstance(item, dict):
            continue
        try:
            skills.append(
                Skill(
                    skill_id=str(item["id"]),
                    key=str(item["key"]),
                    kind=str(item["kind"]),
                    priority=int(item["priority"]),
                    min_targets=int(item["min_targets"]),
                    max_targets=int(item.get("max_targets", 999)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    if not skills:
        return default_selector()
    return CombatSelector(skills=skills)


def _read_yaml(path: str | Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}

    cfg_path = Path(path)
    if not cfg_path.exists():
        return {}

    try:
        content = cfg_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    try:
        loaded = yaml.safe_load(content)
    except Exception:
        return {}

    if isinstance(loaded, dict):
        return loaded
    return {}
