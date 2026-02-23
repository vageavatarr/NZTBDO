from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any

from nztbdo_orchestrator.config import load_profile_config
from nztbdo_orchestrator.cast_verifier import CastVerifier

_ROOT = Path(__file__).resolve().parents[4]
_INPUT_SRC = _ROOT / "services" / "input-control" / "src"
if str(_INPUT_SRC) not in sys.path:
    sys.path.insert(0, str(_INPUT_SRC))
_CAPTURE_SRC = _ROOT / "services" / "capture" / "src"
if str(_CAPTURE_SRC) not in sys.path:
    sys.path.insert(0, str(_CAPTURE_SRC))

from nztbdo_input_control.executor import ActionExecutor
from nztbdo_capture.screen_capture import PrimaryMonitorCapture


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live skill-combo test for configured profile.")
    parser.add_argument("--profile", default="live_farm")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--step-delay", type=float, default=0.5)
    parser.add_argument("--cast-delay", type=float, default=0.45)
    parser.add_argument("--cast-threshold", type=float, default=0.22)
    parser.add_argument("--cast-verify", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def run(
    profile: str,
    repeats: int,
    step_delay: float,
    cast_delay: float,
    cast_threshold: float,
    cast_verify: bool,
) -> dict[str, Any]:
    cfg = load_profile_config(_ROOT, profile)
    thresholds = _read_yaml(cfg.thresholds_path)
    input_cfg = thresholds.get("input_control", {})
    combat_cfg = thresholds.get("combat", {})
    dry_run = bool(input_cfg.get("dry_run", True)) if isinstance(input_cfg, dict) else True
    allowed_titles = input_cfg.get("allowed_window_titles", []) if isinstance(input_cfg, dict) else []
    allowed_processes = input_cfg.get("allowed_process_names", []) if isinstance(input_cfg, dict) else []
    bind_to_process = bool(input_cfg.get("bind_to_process", False)) if isinstance(input_cfg, dict) else False
    allow_background_input = bool(input_cfg.get("allow_background_input", False)) if isinstance(input_cfg, dict) else False
    max_hz = int(combat_cfg.get("action_rate_limit_hz", 6)) if isinstance(combat_cfg, dict) else 6
    post_skill_pause = float(combat_cfg.get("post_skill_pause_sec", 1.5)) if isinstance(combat_cfg, dict) else 1.5

    executor = ActionExecutor(
        max_hz=max_hz,
        dry_run=dry_run,
        allowed_window_substrings=[str(item) for item in allowed_titles if str(item).strip()],
        allowed_process_names=[str(item) for item in allowed_processes if str(item).strip()],
        bind_to_process=bind_to_process,
        allow_background_input=allow_background_input,
    )

    regular_pause = max(step_delay, post_skill_pause + 0.1)
    sequence = [
        ("press_shift_q", regular_pause),
        ("press_hold_q_4s", max(regular_pause, 0.8)),
        ("press_shift_rmb_hold", max(regular_pause, 0.8)),
        ("press_shift_lmb", regular_pause),
        ("press_shift_f", regular_pause),
        ("press_s_lmb", regular_pause),
    ]

    outcomes: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    cast_counts: Counter[str] = Counter()
    cast_details: list[dict[str, Any]] = []
    report_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    debug_dir = _ROOT / "data" / "logs" / "skill_tests" / f"{report_stamp}-assets"
    verifier = CastVerifier(_ROOT, profile=profile)
    capture = PrimaryMonitorCapture() if (cast_verify and verifier.enabled) else None
    total = 0
    performed = 0
    try:
        for idx in range(max(1, repeats)):
            for action, pause_s in sequence:
                total += 1
                result = executor.execute(action)
                if result.performed:
                    performed += 1
                reason_counts[result.reason] += 1
                row: dict[str, Any] = {
                    "iteration": idx + 1,
                    "action": action,
                    "performed": bool(result.performed),
                    "reason": result.reason,
                    "timestamp_ms": int(time.time() * 1000),
                }

                if capture is not None and result.performed:
                    time.sleep(max(0.05, cast_delay))
                    frame = capture.capture_to_png(
                        frames_dir=debug_dir,
                        prefix=f"cast_{idx+1}_{action}",
                        index=total,
                    )
                    crop_path = debug_dir / f"{Path(frame.path).stem}_roi.png"
                    verified = verifier.verify(
                        action=action,
                        frame_path=Path(frame.path),
                        crop_out_path=crop_path,
                        threshold=cast_threshold,
                    )
                    if verified is not None:
                        info = {
                            "action": action,
                            "frame_path": frame.path,
                            "crop_path": verified.crop_path,
                            "expected_template_id": verified.expected_template_id,
                            "best_template_id": verified.best_template_id,
                            "expected_score": verified.expected_score,
                            "best_score": verified.best_score,
                            "detected": verified.detected,
                            "threshold": verified.threshold,
                        }
                        row["cast_verification"] = info
                        cast_details.append(info)
                        cast_counts["checked"] += 1
                        cast_counts["detected" if verified.detected else "missed"] += 1

                outcomes.append(row)
                print(json.dumps(row, ensure_ascii=True))
                time.sleep(max(0.05, pause_s))
    finally:
        if capture is not None:
            capture.close()

    summary = {
        "profile": profile,
        "repeats": max(1, repeats),
        "total_actions": total,
        "performed_actions": performed,
        "success_ratio": round(performed / max(total, 1), 3),
        "reason_counts": dict(reason_counts),
        "dry_run": dry_run,
        "cast_verify_enabled": bool(capture is not None),
        "cast_verify_init_error": verifier.init_error if cast_verify else "",
        "cast_stats": dict(cast_counts),
        "cast_details": cast_details,
        "events": outcomes,
    }
    report_path = _write_report(summary, report_stamp=report_stamp)
    summary["report_path"] = str(report_path)
    return summary


def main() -> None:
    args = parse_args()
    summary = run(
        profile=args.profile,
        repeats=args.repeats,
        step_delay=args.step_delay,
        cast_delay=args.cast_delay,
        cast_threshold=args.cast_threshold,
        cast_verify=bool(args.cast_verify),
    )
    print(json.dumps({"type": "skill_test_summary", **summary}, ensure_ascii=True))


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _write_report(summary: dict[str, Any], report_stamp: str) -> Path:
    reports_dir = _ROOT / "data" / "logs" / "skill_tests"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report_stamp}-skill_test.json"
    path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    main()
