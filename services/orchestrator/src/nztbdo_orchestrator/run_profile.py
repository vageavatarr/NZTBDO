from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import time

from nztbdo_orchestrator.main import Orchestrator, TickInput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NZTBDO synthetic profile loop and write summary.")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--ticks", type=int, default=600)
    parser.add_argument("--tick-sleep", type=float, default=0.05)
    return parser.parse_args()


def generate_tick(idx: int) -> TickInput:
    in_pull = (idx % 20) in {5, 6, 7, 8, 9}
    in_cleanup = (idx % 20) == 10
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
            skill_cd={
                "aoe_around_shift_q_q": 0.0,
                "front_hold_shift_rmb": 0.0,
                "front_shift_lmb": 0.0,
                "front_long_shift_f": 0.0,
                "finisher_s_lmb": 0.0,
            },
        )

    enemies = [(px + random.uniform(4.0, 8.0), py + random.uniform(-2.0, 2.0)) for _ in range(random.randint(2, 6))]
    return TickInput(
        pos_x=px,
        pos_y=py,
        heading_deg=0.0,
        enemy_points=enemies,
        engage_confidence=0.75,
        combat_clear=in_cleanup,
        skill_cd={
            "aoe_around_shift_q_q": 0.0 if idx % 10 == 0 else 6.0,
            "front_hold_shift_rmb": 0.0 if idx % 8 == 0 else 3.0,
            "front_shift_lmb": 0.0 if idx % 7 == 0 else 2.0,
            "front_long_shift_f": 0.0 if idx % 9 == 0 else 4.0,
            "finisher_s_lmb": 0.0,
        },
    )


def run(profile: str, ticks: int, tick_sleep: float) -> dict:
    orchestrator = Orchestrator(profile_name=profile)
    orchestrator.start()
    states = Counter()
    actions = Counter()
    execs = Counter()

    started = time.time()
    for idx in range(1, ticks + 1):
        result = orchestrator.tick(generate_tick(idx))
        states[result.state.value] += 1
        actions[result.action] += 1
        execs[result.execution.reason] += 1
        time.sleep(tick_sleep)
    elapsed = max(time.time() - started, 0.001)

    summary = {
        "profile": profile,
        "session_id": orchestrator.session_id,
        "events_path": str(orchestrator.events_path),
        "ticks": ticks,
        "elapsed_sec": round(elapsed, 3),
        "tps": round(ticks / elapsed, 2),
        "states": dict(states),
        "actions": dict(actions),
        "execution_reasons": dict(execs),
    }
    summary_path = Path(orchestrator.events_path).with_name("summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> None:
    args = parse_args()
    summary = run(profile=args.profile, ticks=args.ticks, tick_sleep=args.tick_sleep)
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
