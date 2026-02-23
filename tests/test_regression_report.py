from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
ORCH_SRC = ROOT / "services" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from nztbdo_orchestrator.regression import evaluate_regression


def test_regression_flags_blocked_ratio_degradation(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    _write_session(
        logs_root / "sess1" / "session_pipeline_summary.json",
        avg_blocked_ratio=0.10,
        guard_blocked_ratio=0.0,
    )
    _write_session(
        logs_root / "sess2" / "session_pipeline_summary.json",
        avg_blocked_ratio=0.12,
        guard_blocked_ratio=0.0,
    )

    current = _current_summary(avg_blocked_ratio=0.35, guard_blocked_ratio=0.0)
    result = evaluate_regression(
        logs_root=logs_root,
        current_session_id="sess3",
        current_summary=current,
        lookback=5,
    )
    assert result.needs_review is True
    assert any("avg_blocked_ratio" in item for item in result.findings)


def _write_session(path: Path, *, avg_blocked_ratio: float, guard_blocked_ratio: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _current_summary(avg_blocked_ratio=avg_blocked_ratio, guard_blocked_ratio=guard_blocked_ratio)
    path.write_text(json.dumps(data), encoding="utf-8")


def _current_summary(*, avg_blocked_ratio: float, guard_blocked_ratio: float) -> dict:
    return {
        "runtime": {
            "ticks": 100,
            "execution_reasons": {"window_guard_blocked": int(guard_blocked_ratio * 100)},
        },
        "training": {
            "metrics": {
                "avg_blocked_ratio": avg_blocked_ratio,
                "action_rationale_distribution": {"aoe_front": 6, "single_target": 4},
            }
        },
    }
