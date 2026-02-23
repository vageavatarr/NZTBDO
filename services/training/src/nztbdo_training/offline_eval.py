from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any


def evaluate_dataset(dataset_file: Path) -> dict[str, Any]:
    if not dataset_file.exists():
        return {
            "rows": 0,
            "avg_confidence": 0.0,
            "avg_blocked_ratio": 0.0,
            "action_rationale_distribution": {},
            "quality_distribution": {},
        }

    rows = 0
    total_conf = 0.0
    total_blocked_ratio = 0.0
    rationale_counts: Counter[str] = Counter()
    quality_counts: Counter[str] = Counter()

    with dataset_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows += 1
            conf = float(row.get("label_confidence", 0.0))
            blocked = float(row.get("blocked_count", 0.0))
            ticks = max(float(row.get("tick_count", 1.0)), 1.0)
            total_conf += conf
            total_blocked_ratio += blocked / ticks
            rationale_counts[str(row.get("label_action_rationale", "unknown"))] += 1
            quality_counts[str(row.get("label_outcome_quality", "unknown"))] += 1

    if rows == 0:
        return {
            "rows": 0,
            "avg_confidence": 0.0,
            "avg_blocked_ratio": 0.0,
            "action_rationale_distribution": {},
            "quality_distribution": {},
        }

    return {
        "rows": rows,
        "avg_confidence": round(total_conf / rows, 4),
        "avg_blocked_ratio": round(total_blocked_ratio / rows, 4),
        "action_rationale_distribution": dict(rationale_counts),
        "quality_distribution": dict(quality_counts),
    }
