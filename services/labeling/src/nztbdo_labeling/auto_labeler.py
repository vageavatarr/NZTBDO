from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from nztbdo_labeling.types import Episode


def auto_label_episode(episode: Episode) -> dict[str, Any]:
    reasons = Counter(event.reason for event in episode.events)
    actions = Counter(event.action for event in episode.events)
    performed_count = sum(1 for event in episode.events if event.execution_performed)
    blocked_count = episode.tick_count - performed_count

    dominant_reason = _pick_dominant_reason(reasons)
    quality = _outcome_quality(performed_count, blocked_count)
    confidence = _confidence_score(reasons, blocked_count, episode.tick_count)

    first_input = episode.events[0].input_data if episode.events else {}
    last_input = episode.events[-1].input_data if episode.events else {}

    return {
        "session_id": episode.session_id,
        "episode_id": episode.episode_id,
        "start_ts_ms": episode.start_ts_ms,
        "end_ts_ms": episode.end_ts_ms,
        "tick_count": episode.tick_count,
        "label": {
            "action_rationale": dominant_reason,
            "outcome_quality": quality,
            "confidence": confidence,
        },
        "stats": {
            "reasons": dict(reasons),
            "actions": dict(actions),
            "performed_count": performed_count,
            "blocked_count": blocked_count,
        },
        "context": {
            "first_input": first_input,
            "last_input": last_input,
        },
        "events": [asdict(event) for event in episode.events],
    }


def _pick_dominant_reason(reasons: Counter[str]) -> str:
    if not reasons:
        return "unknown"
    if reasons.get("front_aoe", 0) > 0:
        return "aoe_front"
    if reasons.get("around_aoe", 0) > 0:
        return "aoe_around"
    if reasons.get("single_target", 0) > 0:
        return "single_target"
    if reasons.get("cooldown_wait", 0) > 0:
        return "wait_cd"
    if reasons.get("no_front_targets", 0) > 0:
        return "reposition"
    return reasons.most_common(1)[0][0]


def _outcome_quality(performed_count: int, blocked_count: int) -> str:
    total = max(performed_count + blocked_count, 1)
    blocked_ratio = blocked_count / total
    if blocked_ratio <= 0.15:
        return "good"
    if blocked_ratio <= 0.40:
        return "neutral"
    return "bad"


def _confidence_score(reasons: Counter[str], blocked_count: int, tick_count: int) -> float:
    if tick_count <= 0:
        return 0.1
    dominant = reasons.most_common(1)[0][1] if reasons else 0
    dominant_ratio = dominant / tick_count
    blocked_ratio = blocked_count / tick_count
    score = 0.35 + 0.45 * dominant_ratio + 0.20 * (1.0 - blocked_ratio)
    if score < 0.05:
        return 0.05
    if score > 0.99:
        return 0.99
    return round(score, 4)
