from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ORCH_SRC = ROOT / "services" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from nztbdo_orchestrator.config import list_profiles, load_profile_config


def test_list_profiles_contains_default() -> None:
    profiles = list_profiles(ROOT)
    assert "default" in profiles
    assert "live_farm" in profiles


def test_load_default_profile_paths() -> None:
    cfg = load_profile_config(ROOT, "default")
    assert cfg.skills_path.exists()
    assert cfg.route_path.exists()
    assert cfg.thresholds_path.exists()


def test_load_live_farm_profile_paths() -> None:
    cfg = load_profile_config(ROOT, "live_farm")
    assert cfg.thresholds_path.name == "thresholds_live_farm.yaml"
    assert cfg.thresholds_path.exists()
