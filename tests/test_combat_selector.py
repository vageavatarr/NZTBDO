from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
COMBAT_SRC = ROOT / "services" / "combat" / "src"
if str(COMBAT_SRC) not in sys.path:
    sys.path.insert(0, str(COMBAT_SRC))

from nztbdo_combat.selector import CombatSnapshot, default_selector


def test_front_aoe_priority() -> None:
    selector = default_selector()
    decision = selector.decide(
        CombatSnapshot(
            enemies_total_near=5,
            enemies_in_front=3,
            skill_cd={"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0},
        )
    )
    assert decision.action == "press_1"
    assert decision.reason == "front_aoe"


def test_single_target_when_aoe_not_available() -> None:
    selector = default_selector()
    decision = selector.decide(
        CombatSnapshot(
            enemies_total_near=1,
            enemies_in_front=1,
            skill_cd={"1": 3.0, "2": 6.0, "3": 0.0, "4": 0.0},
        )
    )
    assert decision.action == "press_3"
    assert decision.reason == "single_target"
