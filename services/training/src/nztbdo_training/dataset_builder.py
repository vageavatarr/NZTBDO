from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any


def collect_episode_files(labels_root: Path) -> list[Path]:
    return sorted(labels_root.glob("*/episodes.jsonl"))


def build_flat_dataset(labels_root: Path, output_file: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    action_rationale_counts: Counter[str] = Counter()
    quality_counts: Counter[str] = Counter()

    for file_path in collect_episode_files(labels_root):
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                flat = _to_flat_row(row)
                rows.append(flat)
                action_rationale_counts[flat["label_action_rationale"]] += 1
                quality_counts[flat["label_outcome_quality"]] += 1

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    return {
        "rows": len(rows),
        "output_file": str(output_file),
        "action_rationale_counts": dict(action_rationale_counts),
        "quality_counts": dict(quality_counts),
    }


def _to_flat_row(row: dict[str, Any]) -> dict[str, Any]:
    label = row.get("label", {})
    stats = row.get("stats", {})
    reasons = stats.get("reasons", {})
    actions = stats.get("actions", {})
    context = row.get("context", {})
    first_input = context.get("first_input", {})
    last_input = context.get("last_input", {})

    return {
        "session_id": row.get("session_id"),
        "episode_id": row.get("episode_id"),
        "start_ts_ms": row.get("start_ts_ms"),
        "end_ts_ms": row.get("end_ts_ms"),
        "tick_count": row.get("tick_count"),
        "label_action_rationale": label.get("action_rationale", "unknown"),
        "label_outcome_quality": label.get("outcome_quality", "unknown"),
        "label_confidence": label.get("confidence", 0.0),
        "performed_count": stats.get("performed_count", 0),
        "blocked_count": stats.get("blocked_count", 0),
        "reason_front_aoe": reasons.get("front_aoe", 0),
        "reason_around_aoe": reasons.get("around_aoe", 0),
        "reason_single_target": reasons.get("single_target", 0),
        "reason_cooldown_wait": reasons.get("cooldown_wait", 0),
        "action_press_1": actions.get("press_1", 0),
        "action_press_2": actions.get("press_2", 0),
        "action_press_3": actions.get("press_3", 0),
        "action_press_4": actions.get("press_4", 0),
        "action_press_shift_q_q": actions.get("press_shift_q_q", 0),
        "action_press_shift_rmb_hold": actions.get("press_shift_rmb_hold", 0),
        "action_press_shift_lmb": actions.get("press_shift_lmb", 0),
        "action_press_shift_f": actions.get("press_shift_f", 0),
        "action_press_s_lmb": actions.get("press_s_lmb", 0),
        "action_press_lmb": actions.get("press_lmb", 0),
        "first_engage_confidence": first_input.get("engage_confidence", 0.0),
        "last_engage_confidence": last_input.get("engage_confidence", 0.0),
    }
