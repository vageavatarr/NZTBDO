from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[4]
_LOGS_ROOT = _ROOT / "data" / "logs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate roadmap milestone acceptance criteria for Perception v1 Productionization + Long-Run Validation."
    )
    parser.add_argument("--logs-root", default=str(_LOGS_ROOT))
    parser.add_argument("--min-soak-sec", type=float, default=3600.0)
    parser.add_argument("--print-sessions", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logs_root = Path(args.logs_root)
    sessions = _load_sessions(logs_root)
    report = _evaluate(sessions, min_soak_sec=float(args.min_soak_sec), print_sessions=max(0, args.print_sessions))
    print(json.dumps(report, ensure_ascii=True, indent=2))


def _load_sessions(logs_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not logs_root.exists():
        return rows
    for session_dir in sorted(logs_root.glob("*")):
        if not session_dir.is_dir():
            continue
        runtime_file = session_dir / "runtime_summary.json"
        pipeline_file = session_dir / "session_pipeline_summary.json"
        regression_file = session_dir / "regression_report.json"
        if not runtime_file.exists():
            continue
        try:
            runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        pipeline = None
        regression = None
        if pipeline_file.exists():
            try:
                pipeline = json.loads(pipeline_file.read_text(encoding="utf-8"))
            except Exception:
                pipeline = None
        if regression_file.exists():
            try:
                regression = json.loads(regression_file.read_text(encoding="utf-8"))
            except Exception:
                regression = None
        rows.append(
            {
                "session_id": session_dir.name,
                "runtime": runtime,
                "pipeline": pipeline,
                "regression": regression,
                "runtime_path": str(runtime_file),
                "pipeline_path": str(pipeline_file),
                "regression_path": str(regression_file),
            }
        )
    return rows


def _evaluate(sessions: list[dict[str, Any]], *, min_soak_sec: float, print_sessions: int) -> dict[str, Any]:
    if not sessions:
        return {
            "milestone": "Perception v1 Productionization + Long-Run Validation",
            "status": "fail",
            "reason": "no_runtime_sessions_found",
            "criteria": {},
            "next_actions": [
                "Run at least one full run_session to generate runtime_summary.json.",
            ],
        }

    latest = sessions[-1]
    backend_ok = any(str(s["runtime"].get("perception_backend", "")) == "ultralytics" for s in sessions)
    no_deadlock_soak = any(float(s["runtime"].get("elapsed_sec", 0.0)) >= min_soak_sec for s in sessions)
    pipeline_artifacts_ok = any(
        s.get("pipeline") is not None
        and Path(s["pipeline_path"]).exists()
        and Path(s["regression_path"]).exists()
        for s in sessions
    )
    review_false_ok = any(
        isinstance(s.get("regression"), dict) and (s["regression"].get("needs_review") is False)
        for s in sessions
    )

    criteria = {
        "backend_ultralytics_seen": backend_ok,
        "one_hour_soak_completed": no_deadlock_soak,
        "pipeline_and_regression_reports_present": pipeline_artifacts_ok,
        "at_least_one_session_needs_review_false": review_false_ok,
    }
    passed = all(criteria.values())
    recent = []
    for s in sessions[-print_sessions:]:
        rt = s["runtime"]
        recent.append(
            {
                "session_id": s["session_id"],
                "elapsed_sec": float(rt.get("elapsed_sec", 0.0)),
                "backend": rt.get("perception_backend"),
                "states": rt.get("states", {}),
                "actions": rt.get("actions", {}),
                "has_pipeline_summary": s.get("pipeline") is not None,
                "needs_review": (s.get("regression") or {}).get("needs_review"),
            }
        )

    next_actions: list[str] = []
    if not no_deadlock_soak:
        next_actions.append("Run one uninterrupted run_session for >= 3600s and keep runtime_summary/session_pipeline_summary/regression_report.")
    if not review_false_ok:
        next_actions.append("Improve guard/pause rate and detection quality, then rerun until regression_report.needs_review=false.")
    if not pipeline_artifacts_ok:
        next_actions.append("Ensure runs complete naturally (avoid manual stop) so pipeline artifacts are written.")
    if not backend_ok:
        next_actions.append("Fix perception backend/model so runtime reports perception_backend=ultralytics.")

    return {
        "milestone": "Perception v1 Productionization + Long-Run Validation",
        "status": "pass" if passed else "in_progress",
        "criteria": criteria,
        "latest_session": {
            "session_id": latest["session_id"],
            "runtime_path": latest["runtime_path"],
            "pipeline_path": latest["pipeline_path"],
            "regression_path": latest["regression_path"],
        },
        "recent_sessions": recent,
        "next_actions": next_actions,
    }


if __name__ == "__main__":
    main()
