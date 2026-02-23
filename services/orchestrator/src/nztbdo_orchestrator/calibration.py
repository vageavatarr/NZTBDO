from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_calibration_report(
    *,
    runtime_summary: dict[str, Any],
    thresholds_path: Path,
) -> dict[str, Any]:
    current_cfg = _read_yaml(thresholds_path)
    perception_cfg = current_cfg.get("perception") if isinstance(current_cfg.get("perception"), dict) else {}
    runtime_cfg = perception_cfg.get("runtime") if isinstance(perception_cfg.get("runtime"), dict) else {}

    backend = str(runtime_summary.get("perception_backend", "unknown"))
    detection = runtime_summary.get("detection_analytics", {})
    if not isinstance(detection, dict):
        detection = {}
    class_counts_raw = detection.get("class_counts", {})
    if not isinstance(class_counts_raw, dict):
        class_counts_raw = {}

    class_counts: dict[int, int] = {}
    for k, v in class_counts_raw.items():
        try:
            cls = int(k)
            cnt = int(v)
        except Exception:
            continue
        class_counts[cls] = cnt

    findings: list[str] = []
    recommendations: dict[str, Any] = {}

    if backend != "ultralytics":
        findings.append("Perception backend is not ultralytics; class/confidence calibration is limited.")
    if not bool(runtime_summary.get("perception_model_exists", False)):
        findings.append("Model file missing: data/models/enemy_detector.pt")
    if not bool(runtime_summary.get("perception_ultralytics_available", False)):
        findings.append("Python package ultralytics is not installed in runtime environment.")

    avg_conf = float(detection.get("avg_confidence", 0.0))
    min_conf = float(detection.get("min_confidence", 0.0))
    max_conf = float(detection.get("max_confidence", 0.0))
    current_conf_min = float(runtime_cfg.get("confidence_min", 0.45))
    if backend == "ultralytics":
        recommended_conf_min = round(max(0.25, min(0.85, avg_conf - 0.10)), 2)
    else:
        recommended_conf_min = current_conf_min

    if recommended_conf_min != current_conf_min:
        findings.append(
            f"Recommend adjusting confidence_min from {current_conf_min:.2f} to {recommended_conf_min:.2f}"
        )

    recommended_enemy_classes = _recommend_enemy_classes(class_counts)
    current_enemy_classes = runtime_cfg.get("enemy_class_ids", [])
    if not isinstance(current_enemy_classes, list):
        current_enemy_classes = []

    if backend == "ultralytics" and recommended_enemy_classes:
        findings.append("Recommend setting enemy_class_ids based on observed dominant classes.")

    recommendations["perception.runtime.confidence_min"] = recommended_conf_min
    recommendations["perception.runtime.enemy_class_ids"] = recommended_enemy_classes

    report = {
        "backend": backend,
        "model_ready": backend == "ultralytics",
        "thresholds_path": str(thresholds_path),
        "current": {
            "confidence_min": current_conf_min,
            "enemy_class_ids": current_enemy_classes,
            "avg_confidence": avg_conf,
            "min_confidence": min_conf,
            "max_confidence": max_conf,
            "class_counts": {str(k): v for k, v in class_counts.items()},
        },
        "recommendations": recommendations,
        "findings": findings,
    }
    return report


def write_calibration_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")


def _recommend_enemy_classes(class_counts: dict[int, int]) -> list[int]:
    filtered = {k: v for k, v in class_counts.items() if k >= 0 and v > 0}
    total = sum(filtered.values())
    if total <= 0:
        return []
    result: list[int] = []
    for cls, cnt in sorted(filtered.items(), key=lambda item: item[1], reverse=True):
        share = cnt / total
        if share >= 0.1:
            result.append(cls)
    return result


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
