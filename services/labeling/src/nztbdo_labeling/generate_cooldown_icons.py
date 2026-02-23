from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate per-second cooldown icon variants from clean icon templates."
    )
    parser.add_argument(
        "--templates-config",
        default="shared/config/cooldown_templates_live_farm.yaml",
        help="YAML with template_id -> skill/action mapping.",
    )
    parser.add_argument(
        "--skills-config",
        default="shared/config/skills.yaml",
        help="YAML with skill cooldown_sec values.",
    )
    parser.add_argument(
        "--icons-dir",
        default="data/raw/cooldown_icons/live_farm/clean",
        help="Folder with clean icon files named <template_id>.png",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed/cooldown_icons/live_farm/generated",
        help="Output folder for generated cooldown frames.",
    )
    parser.add_argument(
        "--labels-file",
        default="data/processed/cooldown_icons/live_farm/labels.jsonl",
        help="Output JSONL labels file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[4]
    templates_cfg = _read_yaml(root / args.templates_config)
    skills_cfg = _read_yaml(root / args.skills_config)
    icons_dir = root / args.icons_dir
    output_dir = root / args.output_dir
    labels_file = root / args.labels_file

    templates = templates_cfg.get("templates", [])
    if not isinstance(templates, list) or not templates:
        raise SystemExit("No templates found in templates config.")

    cooldown_by_skill = _cooldown_map(skills_cfg)

    try:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFont
    except Exception as exc:
        raise SystemExit(f"Pillow is required: pip install pillow ({exc})")

    output_dir.mkdir(parents=True, exist_ok=True)
    labels_file.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    generated = 0
    for item in templates:
        if not isinstance(item, dict):
            continue
        template_id = str(item.get("template_id", "")).strip()
        skill_id = str(item.get("skill_id", "")).strip()
        action = str(item.get("action", "")).strip()
        if not template_id:
            continue

        src = icons_dir / f"{template_id}.png"
        if not src.exists():
            missing.append(template_id)
            continue

        cooldown_sec = _resolve_cooldown_seconds(item, cooldown_by_skill, skill_id)
        icon = Image.open(src).convert("RGBA")

        # Ready state.
        ready_path = output_dir / f"{template_id}_ready.png"
        icon.save(ready_path)
        rows.append(
            _row(template_id, skill_id, action, "ready", 0.0, src, ready_path)
        )
        generated += 1

        if cooldown_sec <= 0:
            continue

        total_sec = max(1, int(math.ceil(cooldown_sec)))
        for sec in range(total_sec, 0, -1):
            frame = _render_cooldown_frame(
                icon=icon,
                remaining_sec=sec,
                total_sec=total_sec,
                ImageDraw=ImageDraw,
                ImageEnhance=ImageEnhance,
                ImageFont=ImageFont,
            )
            out = output_dir / f"{template_id}_cd_{sec:02d}.png"
            frame.save(out)
            rows.append(
                _row(template_id, skill_id, action, "cooling", float(sec), src, out)
            )
            generated += 1

    with labels_file.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    report = {
        "templates_total": len([t for t in templates if isinstance(t, dict)]),
        "generated_files": generated,
        "labels_file": str(labels_file),
        "output_dir": str(output_dir),
        "missing_templates": missing,
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception:
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


def _cooldown_map(skills_cfg: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in skills_cfg.get("skills", []) if isinstance(skills_cfg.get("skills"), list) else []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id", "")).strip()
        if not sid:
            continue
        try:
            out[sid] = float(item.get("cooldown_sec", 0.0))
        except Exception:
            out[sid] = 0.0
    return out


def _resolve_cooldown_seconds(template: dict[str, Any], cooldown_by_skill: dict[str, float], skill_id: str) -> float:
    val = template.get("cooldown_sec")
    if isinstance(val, (int, float)):
        return float(val)
    return float(cooldown_by_skill.get(skill_id, 0.0))


def _render_cooldown_frame(
    *,
    icon,
    remaining_sec: int,
    total_sec: int,
    ImageDraw,
    ImageEnhance,
    ImageFont,
):
    base = icon.copy()

    # Slight darkening for "cooling" state.
    darkened = ImageEnhance.Brightness(base).enhance(0.72)

    # Add radial blackout sector proportional to remaining cooldown.
    w, h = darkened.size
    ratio = max(0.0, min(1.0, float(remaining_sec) / max(float(total_sec), 1.0)))
    overlay = icon.copy()
    overlay.putalpha(0)
    draw = ImageDraw.Draw(overlay, "RGBA")
    start_angle = -90
    end_angle = start_angle + int(360.0 * ratio)
    draw.pieslice((0, 0, w - 1, h - 1), start=start_angle, end=end_angle, fill=(0, 0, 0, 125))
    frame = darkened.copy()
    frame.alpha_composite(overlay)

    # Render remaining seconds.
    draw_f = ImageDraw.Draw(frame, "RGBA")
    text = f"{remaining_sec}c"
    font = ImageFont.load_default()
    tw = int(draw_f.textlength(text, font=font))
    th = 10
    tx = max(1, (w - tw) // 2)
    ty = max(1, (h - th) // 2)
    draw_f.rectangle((tx - 1, ty - 1, tx + tw + 1, ty + th + 1), fill=(0, 0, 0, 120))
    draw_f.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)
    return frame


def _row(
    template_id: str,
    skill_id: str,
    action: str,
    state: str,
    seconds_remaining: float,
    source_path: Path,
    generated_path: Path,
) -> dict[str, Any]:
    return {
        "template_id": template_id,
        "skill_id": skill_id,
        "action": action,
        "cooldown_state": state,
        "cooldown_seconds": seconds_remaining,
        "source_path": str(source_path),
        "generated_path": str(generated_path),
    }


if __name__ == "__main__":
    main()
