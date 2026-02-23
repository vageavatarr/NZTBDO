from __future__ import annotations

from pathlib import Path
from typing import Any


class RuntimePerceptionAdapter:
    """Runtime enemy detector adapter with optional YOLO backend and safe fallback."""

    def __init__(
        self,
        *,
        backend: str = "auto",
        model_path: str = "",
        confidence_min: float = 0.45,
        pixel_to_meter: float = 0.01,
        max_targets: int = 8,
        enemy_class_ids: list[int] | None = None,
    ) -> None:
        self._backend = "stub"
        self._confidence_min = confidence_min
        self._pixel_to_meter = pixel_to_meter
        self._max_targets = max_targets
        self._enemy_class_ids = set(enemy_class_ids or [])
        self._yolo_model: Any | None = None

        if backend in {"auto", "ultralytics"}:
            self._try_init_yolo(model_path)

    @property
    def backend(self) -> str:
        return self._backend

    def detect_enemy_points(
        self,
        *,
        frame_path: str,
        player_x: float,
        player_y: float,
    ) -> list[tuple[float, float]]:
        path = Path(frame_path)
        if not path.exists():
            return []

        if self._yolo_model is not None:
            yolo_points = self._detect_with_yolo(path, player_x, player_y)
            if yolo_points is not None:
                return yolo_points

        size = path.stat().st_size
        pack = int(size % 5)
        if pack == 0:
            return []

        enemies: list[tuple[float, float]] = []
        for idx in range(pack):
            dx = 4.0 + (idx * 0.7)
            dy = -1.5 + ((size + idx) % 7) * 0.5
            enemies.append((player_x + dx, player_y + dy))
        return enemies

    def _try_init_yolo(self, model_path: str) -> None:
        if not model_path:
            return
        model_file = Path(model_path)
        if not model_file.exists():
            return

        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError:
            return

        try:
            self._yolo_model = YOLO(str(model_file))
            self._backend = "ultralytics"
        except Exception:
            self._yolo_model = None
            self._backend = "stub"

    def _detect_with_yolo(
        self,
        frame_path: Path,
        player_x: float,
        player_y: float,
    ) -> list[tuple[float, float]] | None:
        if self._yolo_model is None:
            return None
        try:
            predictions = self._yolo_model.predict(
                source=str(frame_path),
                conf=self._confidence_min,
                verbose=False,
            )
        except Exception:
            return None

        if not predictions:
            return []
        first = predictions[0]

        boxes = getattr(first, "boxes", None)
        orig_shape = getattr(first, "orig_shape", None)
        if boxes is None or orig_shape is None:
            return []

        try:
            frame_h = float(orig_shape[0])
            frame_w = float(orig_shape[1])
        except Exception:
            return []

        items: list[tuple[float, float, float]] = []
        for box in boxes:
            try:
                conf = float(box.conf[0].item())
                cls = int(box.cls[0].item())
                xyxy = box.xyxy[0].tolist()
            except Exception:
                continue

            if conf < self._confidence_min:
                continue
            if self._enemy_class_ids and cls not in self._enemy_class_ids:
                continue
            if len(xyxy) != 4:
                continue
            x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            world_x, world_y = _project_to_world(
                cx=cx,
                cy=cy,
                frame_w=frame_w,
                frame_h=frame_h,
                player_x=player_x,
                player_y=player_y,
                pixel_to_meter=self._pixel_to_meter,
            )
            items.append((conf, world_x, world_y))

        items.sort(key=lambda item: item[0], reverse=True)
        points = [(item[1], item[2]) for item in items[: self._max_targets]]
        return points


def _project_to_world(
    *,
    cx: float,
    cy: float,
    frame_w: float,
    frame_h: float,
    player_x: float,
    player_y: float,
    pixel_to_meter: float,
) -> tuple[float, float]:
    center_x = frame_w / 2.0
    dx_pixels = cx - center_x

    # Simple projection: upper-screen targets are usually farther in front.
    forward_m = max(1.0, (1.0 - (cy / max(frame_h, 1.0))) * 12.0)
    lateral_m = dx_pixels * pixel_to_meter
    return player_x + forward_m, player_y + lateral_m
