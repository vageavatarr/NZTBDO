from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import sys
from typing import Any

from nztbdo_orchestrator.config import load_profile_config

_ROOT = Path(__file__).resolve().parents[4]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Suggest a thresholds YAML patch from the latest calibration report."
    )
    parser.add_argument("--profile", default="live_farm")
    parser.add_argument("--calibration-report", default="")
    parser.add_argument(
        "--write-patch",
        default="",
        help="Optional path to write the suggested unified diff.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_profile_config(_ROOT, args.profile)
    thresholds_path = cfg.thresholds_path
    calibration_path = (
        Path(args.calibration_report) if args.calibration_report else _latest_calibration_report(_ROOT / "data" / "logs")
    )
    if calibration_path is None or not calibration_path.exists():
        print("No calibration_report.json found.")
        return

    thresholds = _read_yaml(thresholds_path)
    calibration = _read_json(calibration_path)
    if not isinstance(thresholds, dict) or not isinstance(calibration, dict):
        print("Failed to parse thresholds or calibration report.")
        return

    patched, changed = _apply_recommendations(thresholds, calibration)
    if not changed:
        print("No suggested changes from calibration report.")
        return

    old_text = thresholds_path.read_text(encoding="utf-8")
    new_text = _dump_yaml(patched)

    diff = "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=str(thresholds_path),
            tofile=f"{thresholds_path} (suggested)",
            lineterm="",
        )
    )
    print(diff)

    if args.write_patch:
        out = Path(args.write_patch)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(diff + "\n", encoding="utf-8")
        print(f"\nSuggested patch written to: {out}")


def _apply_recommendations(thresholds: dict[str, Any], calibration: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    out = _deep_copy_dict(thresholds)
    recommendations = calibration.get("recommendations")
    if not isinstance(recommendations, dict):
        return out, False

    changed = False

    confidence = recommendations.get("perception.runtime.confidence_min")
    if isinstance(confidence, (int, float)):
        out.setdefault("perception", {})
        if isinstance(out["perception"], dict):
            out["perception"].setdefault("runtime", {})
            if isinstance(out["perception"]["runtime"], dict):
                new_value = float(confidence)
                old_value = out["perception"]["runtime"].get("confidence_min")
                if old_value != new_value:
                    changed = True
                    out["perception"]["runtime"]["confidence_min"] = new_value

    enemy_classes = recommendations.get("perception.runtime.enemy_class_ids")
    if isinstance(enemy_classes, list):
        out.setdefault("perception", {})
        if isinstance(out["perception"], dict):
            out["perception"].setdefault("runtime", {})
            if isinstance(out["perception"]["runtime"], dict):
                clean_ids = [int(v) for v in enemy_classes if isinstance(v, (int, float))]
                old_ids = out["perception"]["runtime"].get("enemy_class_ids")
                if old_ids != clean_ids:
                    changed = True
                    out["perception"]["runtime"]["enemy_class_ids"] = clean_ids
    return out, changed


def _latest_calibration_report(logs_root: Path) -> Path | None:
    files = sorted(logs_root.glob("*/calibration_report.json"))
    if not files:
        return None
    return files[-1]


def _read_json(path: Path) -> dict[str, Any]:
    import json

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _dump_yaml(payload: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore
    except ImportError:
        raise RuntimeError("PyYAML is required.")
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)


def _deep_copy_dict(value: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in value.items():
        if isinstance(v, dict):
            out[k] = _deep_copy_dict(v)
        elif isinstance(v, list):
            out[k] = [item for item in v]
        else:
            out[k] = v
    return out


if __name__ == "__main__":
    main()
