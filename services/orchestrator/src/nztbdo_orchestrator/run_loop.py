from __future__ import annotations

from collections import Counter
import random
import time

from nztbdo_orchestrator.main import Orchestrator, TickInput


def generate_tick(idx: int) -> TickInput:
    # Simple synthetic world used for soak-style dry runs.
    in_pull = (idx % 20) in {5, 6, 7, 8, 9}
    in_cleanup = (idx % 20) in {10}

    px = float(idx % 40)
    py = float((idx * 2) % 40)

    if not in_pull and not in_cleanup:
        return TickInput(
            pos_x=px,
            pos_y=py,
            heading_deg=0.0,
            enemy_points=[],
            engage_confidence=0.0,
            combat_clear=False,
            skill_cd={"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0},
        )

    enemies = []
    pack = random.randint(2, 6)
    for _ in range(pack):
        enemies.append((px + random.uniform(4.0, 8.0), py + random.uniform(-2.0, 2.0)))

    return TickInput(
        pos_x=px,
        pos_y=py,
        heading_deg=0.0,
        enemy_points=enemies,
        engage_confidence=0.75,
        combat_clear=in_cleanup,
        skill_cd={
            "1": 0.0 if idx % 3 == 0 else 2.0,
            "2": 0.0 if idx % 5 == 0 else 3.0,
            "3": 0.0,
            "4": 0.0 if idx % 7 == 0 else 8.0,
        },
    )


def main() -> None:
    orchestrator = Orchestrator()
    orchestrator.start()
    counters = Counter()
    action_counters = Counter()

    ticks = 200
    tick_sleep_sec = 0.05
    started = time.time()
    for idx in range(1, ticks + 1):
        tick_input = generate_tick(idx)
        result = orchestrator.tick(tick_input)
        counters[result.state.value] += 1
        action_counters[result.action] += 1
        if result.action.startswith("press_"):
            counters["skill_attempts"] += 1
        if result.execution.performed:
            counters["executed"] += 1
        else:
            counters["blocked"] += 1
        time.sleep(tick_sleep_sec)

    elapsed = max(time.time() - started, 0.001)
    print("run_loop summary")
    print(f"ticks={ticks} elapsed_sec={elapsed:.3f} tps={ticks/elapsed:.1f}")
    print(f"states={dict(counters)}")
    print(f"actions={dict(action_counters)}")


if __name__ == "__main__":
    main()
