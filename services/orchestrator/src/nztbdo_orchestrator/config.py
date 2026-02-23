from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OrchestratorConfig:
    skills_path: Path
    route_path: Path
    thresholds_path: Path
    hotkeys_path: Path
    profile_id: str


def load_profile_config(root: Path, profile_name: str = "default") -> OrchestratorConfig:
    profile_path = root / "shared" / "config" / "profiles" / f"{profile_name}.yaml"
    profile = _read_yaml(profile_path)
    cfg = profile.get("config")
    if not isinstance(cfg, dict):
        return _default_config(root, profile_name)

    return OrchestratorConfig(
        skills_path=_resolve(root, cfg.get("skills"), "shared/config/skills.yaml"),
        route_path=_resolve(root, cfg.get("route"), "shared/config/route.yaml"),
        thresholds_path=_resolve(root, cfg.get("thresholds"), "shared/config/thresholds.yaml"),
        hotkeys_path=_resolve(root, cfg.get("hotkeys"), "shared/config/hotkeys.yaml"),
        profile_id=str(profile.get("profile_id", profile_name)),
    )


def list_profiles(root: Path) -> list[str]:
    folder = root / "shared" / "config" / "profiles"
    if not folder.exists():
        return ["default"]
    names = [p.stem for p in folder.glob("*.yaml")]
    if not names:
        return ["default"]
    return sorted(set(names))


def _default_config(root: Path, profile_id: str) -> OrchestratorConfig:
    return OrchestratorConfig(
        skills_path=root / "shared" / "config" / "skills.yaml",
        route_path=root / "shared" / "config" / "route.yaml",
        thresholds_path=root / "shared" / "config" / "thresholds.yaml",
        hotkeys_path=root / "shared" / "config" / "hotkeys.yaml",
        profile_id=profile_id,
    )


def _resolve(root: Path, raw: Any, fallback: str) -> Path:
    if isinstance(raw, str) and raw.strip():
        return root / raw
    return root / fallback


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
