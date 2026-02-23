from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from nztbdo_orchestrator.runtime_loop import run as run_runtime
from nztbdo_orchestrator.regression import evaluate_regression, write_regression_report
from nztbdo_orchestrator.calibration import generate_calibration_report, write_calibration_report
from nztbdo_orchestrator.config import load_profile_config

_ROOT = Path(__file__).resolve().parents[4]
_LABELING_SRC = _ROOT / "services" / "labeling" / "src"
if str(_LABELING_SRC) not in sys.path:
    sys.path.insert(0, str(_LABELING_SRC))

_TRAINING_SRC = _ROOT / "services" / "training" / "src"
if str(_TRAINING_SRC) not in sys.path:
    sys.path.insert(0, str(_TRAINING_SRC))

from nztbdo_labeling.pipeline import run_labeling_for_session
from nztbdo_training.dataset_builder import build_flat_dataset
from nztbdo_training.offline_eval import evaluate_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full NZTBDO session pipeline: runtime -> labeling -> training."
    )
    parser.add_argument("--profile", default="default")
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--tick-sleep", type=float, default=0.05)
    parser.add_argument("--start-delay", type=float, default=0.0)
    parser.add_argument("--pre-ticks", type=int, default=2)
    parser.add_argument("--post-ticks", type=int, default=2)
    parser.add_argument("--labels-root", default=str(_ROOT / "data" / "labels"))
    parser.add_argument("--dataset-file", default=str(_ROOT / "data" / "processed" / "dataset_v1.jsonl"))
    parser.add_argument("--metrics-file", default=str(_ROOT / "data" / "processed" / "metrics_v1.json"))
    parser.add_argument("--quiet-runtime", action="store_true")
    return parser.parse_args()


def run_session(args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_profile_config(_ROOT, args.profile)
    runtime_summary = run_runtime(
        profile_name=args.profile,
        ticks=args.ticks,
        tick_sleep=args.tick_sleep,
        verbose=not args.quiet_runtime,
        start_delay=args.start_delay,
    )

    events_path = Path(runtime_summary["events_path"])
    labels_root = Path(args.labels_root)
    labeling = run_labeling_for_session(
        events_path=events_path,
        labels_root=labels_root,
        pre_ticks=args.pre_ticks,
        post_ticks=args.post_ticks,
    )

    dataset_file = Path(args.dataset_file)
    metrics_file = Path(args.metrics_file)
    dataset_summary = build_flat_dataset(labels_root, dataset_file)
    metrics = evaluate_dataset(dataset_file)
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_file.write_text(json.dumps(metrics, ensure_ascii=True, indent=2), encoding="utf-8")

    session_summary = {
        "runtime": runtime_summary,
        "labeling": {
            "session_id": labeling.session_id,
            "events_total": labeling.events_total,
            "episodes_total": labeling.episodes_total,
            "output_path": str(labeling.output_path),
        },
        "training": {
            "dataset_summary": dataset_summary,
            "metrics": metrics,
            "metrics_file": str(metrics_file),
        },
    }

    regression = evaluate_regression(
        logs_root=_ROOT / "data" / "logs",
        current_session_id=str(runtime_summary["session_id"]),
        current_summary=session_summary,
        lookback=5,
    )
    regression_report_path = events_path.with_name("regression_report.json")
    write_regression_report(regression_report_path, regression)
    session_summary["regression"] = {
        "needs_review": regression.needs_review,
        "findings": regression.findings,
        "baseline_sessions": regression.baseline_sessions,
        "report_path": str(regression_report_path),
    }

    calibration_report = generate_calibration_report(
        runtime_summary=runtime_summary,
        thresholds_path=cfg.thresholds_path,
    )
    calibration_report_path = events_path.with_name("calibration_report.json")
    write_calibration_report(calibration_report_path, calibration_report)
    session_summary["calibration"] = {
        "model_ready": calibration_report.get("model_ready", False),
        "findings": calibration_report.get("findings", []),
        "report_path": str(calibration_report_path),
    }

    session_summary_path = events_path.with_name("session_pipeline_summary.json")
    session_summary_path.write_text(
        json.dumps(session_summary, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    session_summary["session_pipeline_summary_path"] = str(session_summary_path)
    return session_summary


def main() -> None:
    args = parse_args()
    summary = run_session(args)
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
