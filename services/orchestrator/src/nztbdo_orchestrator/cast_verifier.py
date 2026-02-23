from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CastVerification:
    action: str
    expected_template_id: str
    best_template_id: str
    expected_score: float
    best_score: float
    detected: bool
    threshold: float
    crop_path: str


class CastVerifier:
    def __init__(self, root: Path, profile: str = "live_farm") -> None:
        self._root = root
        self._profile = profile
        self._enabled = False
        self._roi: dict[str, float] = {}
        self._action_to_template: dict[str, str] = {}
        self._templates: dict[str, np.ndarray] = {}
        self._template_ids: list[str] = []
        self._init_error = ""

        cfg_path = self._root / "shared" / "config" / f"cast_templates_{profile}.yaml"
        if not cfg_path.exists():
            self._init_error = f"cast templates config not found: {cfg_path}"
            return

        cfg = _read_yaml(cfg_path)
        templates = cfg.get("templates", [])
        roi = cfg.get("roi", {})
        if not isinstance(templates, list) or not templates:
            self._init_error = "cast templates list is empty"
            return
        if not isinstance(roi, dict):
            self._init_error = "cast roi section missing"
            return

        self._roi = {
            "x_norm": float(roi.get("x_norm", 0.5)),
            "y_norm": float(roi.get("y_norm", 0.8)),
            "width_norm": float(roi.get("width_norm", 0.4)),
            "height_norm": float(roi.get("height_norm", 0.18)),
        }

        icons_dir = self._root / "data" / "raw" / "cooldown_icons" / profile / "clean"
        try:
            from PIL import Image
        except Exception as exc:
            self._init_error = f"Pillow import failed: {exc}"
            return

        for row in templates:
            if not isinstance(row, dict):
                continue
            template_id = str(row.get("template_id", "")).strip()
            action = str(row.get("action", "")).strip()
            if not template_id or not action:
                continue
            p = icons_dir / f"{template_id}.png"
            if not p.exists():
                continue
            with Image.open(p) as im:
                arr = _prepare_array(im)
            self._templates[template_id] = arr
            self._action_to_template[action] = template_id
            self._template_ids.append(template_id)

        self._enabled = bool(self._templates) and bool(self._action_to_template)
        if not self._enabled and not self._init_error:
            self._init_error = "no cast templates loaded"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def init_error(self) -> str:
        return self._init_error

    def verify(
        self,
        action: str,
        frame_path: Path,
        crop_out_path: Path,
        threshold: float,
    ) -> CastVerification | None:
        if not self._enabled:
            return None
        expected = self._action_to_template.get(action, "")
        if not expected:
            return None

        try:
            from PIL import Image
        except Exception:
            return None

        with Image.open(frame_path) as frame:
            crop = _crop_by_norm(frame, self._roi)
            crop_arr = _prepare_array(crop)
            crop_out_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(crop_out_path)

        expected_score = _score(crop_arr, self._templates.get(expected, crop_arr))
        best_template = expected
        best_score = expected_score
        for template_id in self._template_ids:
            score = _score(crop_arr, self._templates[template_id])
            if score > best_score:
                best_score = score
                best_template = template_id

        detected = expected_score >= threshold
        return CastVerification(
            action=action,
            expected_template_id=expected,
            best_template_id=best_template,
            expected_score=round(expected_score, 4),
            best_score=round(best_score, 4),
            detected=detected,
            threshold=round(threshold, 4),
            crop_path=str(crop_out_path),
        )


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _crop_by_norm(image: Any, roi: dict[str, float]) -> Any:
    width, height = image.size
    cx = float(roi.get("x_norm", 0.5)) * width
    cy = float(roi.get("y_norm", 0.8)) * height
    rw = max(1.0, float(roi.get("width_norm", 0.4)) * width)
    rh = max(1.0, float(roi.get("height_norm", 0.18)) * height)
    left = int(round(cx - rw / 2))
    top = int(round(cy - rh / 2))
    right = int(round(cx + rw / 2))
    bottom = int(round(cy + rh / 2))
    left = max(0, min(left, width - 1))
    top = max(0, min(top, height - 1))
    right = max(left + 1, min(right, width))
    bottom = max(top + 1, min(bottom, height))
    return image.crop((left, top, right, bottom))


def _prepare_array(image: Any) -> np.ndarray:
    arr = np.asarray(image.convert("L"), dtype=np.float32)
    # Fixed size makes template/frame comparisons stable across resolutions.
    try:
        from PIL import Image

        im = Image.fromarray(arr.astype(np.uint8), mode="L").resize((256, 128))
        arr = np.asarray(im, dtype=np.float32)
    except Exception:
        pass
    return arr


def _score(frame_arr: np.ndarray, template_arr: np.ndarray) -> float:
    a = _normalize(frame_arr)
    b = _normalize(template_arr)
    lum = _corr(a, b)
    edge_a = _edge(a)
    edge_b = _edge(b)
    edge = _corr(edge_a, edge_b)
    # Edge correlation is weighted higher because cast text effects flicker in brightness.
    return float((0.4 * lum) + (0.6 * edge))


def _normalize(arr: np.ndarray) -> np.ndarray:
    if arr.shape != (256, 128):
        try:
            from PIL import Image

            im = Image.fromarray(arr.astype(np.uint8), mode="L").resize((256, 128))
            arr = np.asarray(im, dtype=np.float32)
        except Exception:
            arr = arr.astype(np.float32)
    return arr


def _edge(arr: np.ndarray) -> np.ndarray:
    gx = np.abs(arr - np.roll(arr, 1, axis=1))
    gy = np.abs(arr - np.roll(arr, 1, axis=0))
    return gx + gy


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    x = a - float(np.mean(a))
    y = b - float(np.mean(b))
    denom = float(np.sqrt((x * x).sum()) * np.sqrt((y * y).sum()))
    if denom <= 1e-9:
        return 0.0
    raw = float((x * y).sum() / denom)
    # map [-1, 1] -> [0, 1]
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))
