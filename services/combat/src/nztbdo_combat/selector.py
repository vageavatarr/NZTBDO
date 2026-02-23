from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    skill_id: str
    key: str
    kind: str
    priority: int
    min_targets: int


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
        front_ready = self._ready_candidates(
            kinds={"cone", "line"},
            targets=snapshot.enemies_in_front,
            cooldowns=snapshot.skill_cd,
        )
        if front_ready:
            return Decision(action=f"press_{front_ready[0].key}", reason="front_aoe")

        around_ready = self._ready_candidates(
            kinds={"circle"},
            targets=snapshot.enemies_total_near,
            cooldowns=snapshot.skill_cd,
        )
        if around_ready:
            return Decision(action=f"press_{around_ready[0].key}", reason="around_aoe")

        single_ready = self._ready_candidates(
            kinds={"single"},
            targets=snapshot.enemies_total_near,
            cooldowns=snapshot.skill_cd,
        )
        if single_ready:
            return Decision(action=f"press_{single_ready[0].key}", reason="single_target")

        if snapshot.enemies_total_near > 0 and snapshot.enemies_in_front == 0:
            return Decision(action="reposition", reason="no_front_targets")

        if snapshot.enemies_total_near > 0:
            return Decision(action="wait_cd", reason="cooldown_wait")

        return Decision(action="patrol_move", reason="no_enemies")

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
            if cooldowns.get(skill.key, 999.0) > 0:
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
            ),
            Skill(
                skill_id="whirlwind",
                key="2",
                kind="circle",
                priority=80,
                min_targets=4,
            ),
            Skill(
                skill_id="strike",
                key="3",
                kind="single",
                priority=70,
                min_targets=1,
            ),
            Skill(
                skill_id="execute",
                key="4",
                kind="single",
                priority=60,
                min_targets=1,
            ),
        ]
    )
