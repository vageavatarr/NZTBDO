from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RegressionResult:
    needs_review: bool
    findings: list[str]
    baseline_sessions: int
    metrics: dict[str, Any]
    thresholds: dict[str, float]


def evaluate_regression(
    *,
    logs_root: Path,
    current_session_id: str,
    current_summary: dict[str, Any],
    lookback: int = 5,
) -> RegressionResult:
    previous = _load_previous_pipeline_summaries(logs_root, current_session_id=current_session_id, lookback=lookback)
    if not previous:
        return RegressionResult(
            needs_review=False,
            findings=[],
            baseline_sessions=0,
            metrics={"reason": "no_baseline"},
            thresholds=_default_thresholds(),
        )

    thresholds = _default_thresholds()
    baseline = _baseline_from_previous(previous)
    current = _extract_current_metrics(current_summary)

    findings: list[str] = []
    if current["guard_blocked_ratio"] > max(thresholds["guard_blocked_ratio_hard"], baseline["guard_blocked_ratio"] + thresholds["guard_blocked_delta"]):
        findings.append(
            f"window_guard_blocked_ratio {current['guard_blocked_ratio']:.3f} > baseline {baseline['guard_blocked_ratio']:.3f}"
        )

    if current["avg_blocked_ratio"] > baseline["avg_blocked_ratio"] + thresholds["avg_blocked_delta"]:
        findings.append(
            f"avg_blocked_ratio {current['avg_blocked_ratio']:.3f} > baseline {baseline['avg_blocked_ratio']:.3f}"
        )

    dist_shift = _distribution_shift(current["action_rationale_dist"], baseline["action_rationale_dist"])
    if dist_shift > thresholds["action_dist_shift_max"]:
        findings.append(
            f"action_rationale_shift {dist_shift:.3f} > threshold {thresholds['action_dist_shift_max']:.3f}"
        )

    return RegressionResult(
        needs_review=bool(findings),
        findings=findings,
        baseline_sessions=len(previous),
        metrics={
            "current": current,
            "baseline": baseline,
            "action_rationale_shift": round(dist_shift, 4),
        },
        thresholds=thresholds,
    )


def write_regression_report(path: Path, result: RegressionResult) -> None:
    payload = {
        "needs_review": result.needs_review,
        "findings": result.findings,
        "baseline_sessions": result.baseline_sessions,
        "metrics": result.metrics,
        "thresholds": result.thresholds,
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _load_previous_pipeline_summaries(logs_root: Path, *, current_session_id: str, lookback: int) -> list[dict[str, Any]]:
    files = sorted(logs_root.glob("*/session_pipeline_summary.json"))
    rows: list[dict[str, Any]] = []
    for file in files:
        session_id = file.parent.name
        if session_id == current_session_id:
            continue
        try:
            loaded = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(loaded, dict):
            rows.append(loaded)
    if len(rows) <= lookback:
        return rows
    return rows[-lookback:]


def _extract_current_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    runtime = summary.get("runtime", {})
    training = summary.get("training", {})
    metrics = training.get("metrics", {})
    execution_reasons = runtime.get("execution_reasons", {})
    ticks = max(float(runtime.get("ticks", 1)), 1.0)
    guard_blocked = float(execution_reasons.get("window_guard_blocked", 0.0))
    action_dist_raw = metrics.get("action_rationale_distribution", {})
    return {
        "guard_blocked_ratio": round(guard_blocked / ticks, 4),
        "avg_blocked_ratio": float(metrics.get("avg_blocked_ratio", 0.0)),
        "action_rationale_dist": _normalize_dist(action_dist_raw if isinstance(action_dist_raw, dict) else {}),
    }


def _baseline_from_previous(previous: list[dict[str, Any]]) -> dict[str, Any]:
    guard_values: list[float] = []
    blocked_values: list[float] = []
    action_sum: dict[str, float] = {}
    for item in previous:
        extracted = _extract_current_metrics(item)
        guard_values.append(extracted["guard_blocked_ratio"])
        blocked_values.append(extracted["avg_blocked_ratio"])
        for k, v in extracted["action_rationale_dist"].items():
            action_sum[k] = action_sum.get(k, 0.0) + float(v)

    denom = max(len(previous), 1)
    action_avg = {k: (v / denom) for k, v in action_sum.items()}
    return {
        "guard_blocked_ratio": sum(guard_values) / max(len(guard_values), 1),
        "avg_blocked_ratio": sum(blocked_values) / max(len(blocked_values), 1),
        "action_rationale_dist": _normalize_dist(action_avg),
    }


def _distribution_shift(current: dict[str, float], baseline: dict[str, float]) -> float:
    keys = set(current) | set(baseline)
    if not keys:
        return 0.0
    tv = 0.0
    for key in keys:
        tv += abs(current.get(key, 0.0) - baseline.get(key, 0.0))
    return 0.5 * tv


def _normalize_dist(raw: dict[str, Any]) -> dict[str, float]:
    total = 0.0
    cleaned: dict[str, float] = {}
    for k, v in raw.items():
        value = float(v)
        if value < 0:
            continue
        cleaned[str(k)] = value
        total += value
    if total <= 0:
        return {}
    return {k: (v / total) for k, v in cleaned.items()}


def _default_thresholds() -> dict[str, float]:
    return {
        "guard_blocked_delta": 0.10,
        "guard_blocked_ratio_hard": 0.10,
        "avg_blocked_delta": 0.10,
        "action_dist_shift_max": 0.35,
    }
