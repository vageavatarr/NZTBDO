from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Any

from nztbdo_combat.selector import CombatSnapshot, Decision


@dataclass(frozen=True)
class PendingFeedback:
    context_key: str
    action: str
    execution_performed: bool
    execution_reason: str
    enemies_before: int


class OnlineSkillBandit:
    """Contextual epsilon-greedy bandit for safe online skill policy tuning."""

    def __init__(
        self,
        *,
        policy_path: Path,
        enabled: bool,
        epsilon_start: float = 0.18,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.9995,
        seed: int = 42,
    ) -> None:
        self._policy_path = policy_path
        self.enabled = bool(enabled)
        self._epsilon = max(0.0, float(epsilon_start))
        self._epsilon_min = max(0.0, float(epsilon_min))
        self._epsilon_decay = min(1.0, max(0.9, float(epsilon_decay)))
        self._rng = random.Random(seed)

        self._table: dict[str, dict[str, dict[str, float]]] = {}
        self._stats: dict[str, int | float] = {
            "select_calls": 0,
            "explore_calls": 0,
            "exploit_calls": 0,
            "updates": 0,
            "reward_sum": 0.0,
        }
        self._dirty = False
        self._load()

    def select(self, snapshot: CombatSnapshot, candidates: list[Decision]) -> Decision:
        if not candidates:
            return Decision(action="wait_cd", reason="cooldown_wait")
        default = candidates[0]
        if not self.enabled:
            return default

        press_candidates = [c for c in candidates if c.action.startswith("press_")]
        if not press_candidates:
            return default

        self._stats["select_calls"] = int(self._stats["select_calls"]) + 1
        ctx = self.context_key(snapshot)
        row = self._table.setdefault(ctx, {})

        for c in press_candidates:
            row.setdefault(c.action, {"n": 0.0, "q": 0.0})

        epsilon_now = max(self._epsilon_min, self._epsilon)
        explore = self._rng.random() < epsilon_now
        self._epsilon = max(self._epsilon_min, self._epsilon * self._epsilon_decay)

        if explore:
            self._stats["explore_calls"] = int(self._stats["explore_calls"]) + 1
            choice = self._rng.choice(press_candidates)
            return Decision(action=choice.action, reason=f"{choice.reason}|online_explore")

        self._stats["exploit_calls"] = int(self._stats["exploit_calls"]) + 1
        best = press_candidates[0]
        best_q = float("-inf")
        for c in press_candidates:
            q = float(row[c.action].get("q", 0.0))
            if q > best_q:
                best_q = q
                best = c
        return Decision(action=best.action, reason=f"{best.reason}|online_exploit")

    def make_feedback(
        self,
        snapshot: CombatSnapshot,
        action: str,
        execution_performed: bool,
        execution_reason: str,
    ) -> PendingFeedback | None:
        if not self.enabled:
            return None
        if not action.startswith("press_"):
            return None
        return PendingFeedback(
            context_key=self.context_key(snapshot),
            action=action,
            execution_performed=bool(execution_performed),
            execution_reason=execution_reason,
            enemies_before=int(snapshot.enemies_total_near),
        )

    def update(
        self,
        pending: PendingFeedback,
        *,
        enemies_now: int,
        combat_clear: bool,
    ) -> float:
        if not self.enabled:
            return 0.0
        reward = self._reward(
            pending=pending,
            enemies_now=int(enemies_now),
            combat_clear=bool(combat_clear),
        )
        row = self._table.setdefault(pending.context_key, {})
        slot = row.setdefault(pending.action, {"n": 0.0, "q": 0.0})
        n = float(slot.get("n", 0.0)) + 1.0
        q_old = float(slot.get("q", 0.0))
        q_new = q_old + ((reward - q_old) / max(1.0, n))
        slot["n"] = n
        slot["q"] = q_new
        self._stats["updates"] = int(self._stats["updates"]) + 1
        self._stats["reward_sum"] = float(self._stats["reward_sum"]) + reward
        self._dirty = True
        if int(self._stats["updates"]) % 20 == 0:
            self.save()
        return reward

    def context_key(self, snapshot: CombatSnapshot) -> str:
        near = min(6, max(0, int(snapshot.enemies_total_near)))
        front = min(6, max(0, int(snapshot.enemies_in_front)))
        return f"near={near}|front={front}"

    def summary(self) -> dict[str, Any]:
        rows = sum(1 for _ in self._table)
        actions = sum(len(v) for v in self._table.values())
        updates = int(self._stats["updates"])
        reward_sum = float(self._stats["reward_sum"])
        return {
            "enabled": self.enabled,
            "epsilon": round(self._epsilon, 5),
            "contexts": rows,
            "actions": actions,
            "select_calls": int(self._stats["select_calls"]),
            "explore_calls": int(self._stats["explore_calls"]),
            "exploit_calls": int(self._stats["exploit_calls"]),
            "updates": updates,
            "avg_reward": round(reward_sum / max(1, updates), 4),
            "policy_path": str(self._policy_path),
        }

    def save(self) -> None:
        if not self.enabled:
            return
        if not self._dirty and self._policy_path.exists():
            return
        self._policy_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "epsilon": self._epsilon,
            "table": self._table,
            "stats": self._stats,
        }
        self._policy_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        self._dirty = False

    def _load(self) -> None:
        if not self.enabled or not self._policy_path.exists():
            return
        try:
            loaded = json.loads(self._policy_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(loaded, dict):
            return
        table = loaded.get("table")
        stats = loaded.get("stats")
        epsilon = loaded.get("epsilon")
        if isinstance(table, dict):
            self._table = table
        if isinstance(stats, dict):
            for k, v in stats.items():
                if isinstance(v, (int, float)):
                    self._stats[k] = v
        if isinstance(epsilon, (int, float)):
            self._epsilon = max(self._epsilon_min, float(epsilon))

    @staticmethod
    def _reward(pending: PendingFeedback, *, enemies_now: int, combat_clear: bool) -> float:
        reward = 0.0
        if pending.execution_performed:
            reward += 0.2
        else:
            reward -= 0.35
        if pending.execution_reason.startswith("bg_"):
            reward -= 0.2
        if pending.execution_reason == "window_guard_blocked":
            reward -= 0.35

        delta = int(pending.enemies_before) - int(enemies_now)
        if delta > 0:
            reward += min(1.0, 0.35 * delta)
        elif delta < 0:
            reward -= min(0.6, 0.2 * abs(delta))

        if combat_clear:
            reward += 1.4
        return reward
