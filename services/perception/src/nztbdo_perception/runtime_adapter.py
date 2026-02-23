from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrackedPoint:
    track_id: int
    x: float
    y: float


class WorldPointTracker:
    """Simple nearest-neighbor tracker for stable IDs across frames."""

    def __init__(self, match_distance: float = 2.0, max_missed: int = 6, smoothing: float = 0.35) -> None:
        self._match_distance = max(match_distance, 0.01)
        self._max_missed = max(max_missed, 1)
        self._smoothing = min(max(smoothing, 0.0), 1.0)
        self._next_id = 1
        self._tracks: dict[int, dict[str, float]] = {}

    def update(self, detections: list[tuple[float, float]]) -> list[TrackedPoint]:
        for state in self._tracks.values():
            state["missed"] += 1.0
            state["updated"] = 0.0

        assigned: set[int] = set()
        for det_x, det_y in detections:
            best_id = -1
            best_dist = self._match_distance
            for track_id, state in self._tracks.items():
                if track_id in assigned:
                    continue
                dist = _dist(det_x, det_y, state["x"], state["y"])
                if dist <= best_dist:
                    best_dist = dist
                    best_id = track_id

            if best_id == -1:
                self._tracks[self._next_id] = {
                    "x": det_x,
                    "y": det_y,
                    "missed": 0.0,
                    "updated": 1.0,
                }
                assigned.add(self._next_id)
                self._next_id += 1
                continue

            state = self._tracks[best_id]
            alpha = self._smoothing
            state["x"] = (1.0 - alpha) * state["x"] + alpha * det_x
            state["y"] = (1.0 - alpha) * state["y"] + alpha * det_y
            state["missed"] = 0.0
            state["updated"] = 1.0
            assigned.add(best_id)

        to_delete = [track_id for track_id, state in self._tracks.items() if state["missed"] > self._max_missed]
        for track_id in to_delete:
            del self._tracks[track_id]

        updated_tracks = [
            TrackedPoint(track_id=track_id, x=state["x"], y=state["y"])
            for track_id, state in self._tracks.items()
            if state.get("updated", 0.0) > 0.0
        ]
        updated_tracks.sort(key=lambda item: item.track_id)
        return updated_tracks


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
        self._requested_backend = backend
        self._model_path = model_path
        self._backend = "stub"
        self._confidence_min = confidence_min
        self._pixel_to_meter = pixel_to_meter
        self._max_targets = max_targets
        self._enemy_class_ids = set(enemy_class_ids or [])
        self._yolo_model: Any | None = None
        self._ultralytics_available = False
        self._model_exists = bool(model_path and Path(model_path).exists())
        self._init_reason = "stub_default"
        self._tracker = WorldPointTracker()
        self._last_track_ids: list[int] = []
        self._last_confidences: list[float] = []
        self._last_class_ids: list[int] = []

        if backend in {"auto", "ultralytics"}:
            self._try_init_yolo(model_path)

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def requested_backend(self) -> str:
        return self._requested_backend

    @property
    def model_path(self) -> str:
        return self._model_path

    @property
    def ultralytics_available(self) -> bool:
        return self._ultralytics_available

    @property
    def model_exists(self) -> bool:
        return self._model_exists

    @property
    def init_reason(self) -> str:
        return self._init_reason

    @property
    def last_track_ids(self) -> list[int]:
        return list(self._last_track_ids)

    @property
    def last_confidences(self) -> list[float]:
        return list(self._last_confidences)

    @property
    def last_class_ids(self) -> list[int]:
        return list(self._last_class_ids)

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

        raw_points: list[tuple[float, float]]
        confidences: list[float]
        class_ids: list[int]
        if self._yolo_model is not None:
            yolo_result = self._detect_with_yolo(path, player_x, player_y)
            if yolo_result is not None:
                raw_points, confidences, class_ids = yolo_result
            else:
                raw_points = self._detect_with_stub(path, player_x, player_y)
                confidences = [1.0] * len(raw_points)
                class_ids = [-1] * len(raw_points)
        else:
            raw_points = self._detect_with_stub(path, player_x, player_y)
            confidences = [1.0] * len(raw_points)
            class_ids = [-1] * len(raw_points)

        tracks = self._tracker.update(raw_points)
        self._last_track_ids = [item.track_id for item in tracks]
        self._last_confidences = confidences[: self._max_targets]
        self._last_class_ids = class_ids[: self._max_targets]
        return [(item.x, item.y) for item in tracks]

    def _detect_with_stub(
        self,
        frame_path: Path,
        player_x: float,
        player_y: float,
    ) -> list[tuple[float, float]]:
        size = frame_path.stat().st_size
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
            self._init_reason = "model_path_missing"
            return
        model_file = Path(model_path)
        if not model_file.exists():
            self._init_reason = "model_file_not_found"
            return

        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError:
            self._init_reason = "ultralytics_not_installed"
            return

        self._ultralytics_available = True
        try:
            self._yolo_model = YOLO(str(model_file))
            self._backend = "ultralytics"
            self._init_reason = "ultralytics_ready"
        except Exception:
            self._yolo_model = None
            self._backend = "stub"
            self._init_reason = "ultralytics_init_failed"

    def _detect_with_yolo(
        self,
        frame_path: Path,
        player_x: float,
        player_y: float,
    ) -> tuple[list[tuple[float, float]], list[float], list[int]] | None:
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

        items: list[tuple[float, int, float, float]] = []
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
            items.append((conf, cls, world_x, world_y))

        items.sort(key=lambda item: item[0], reverse=True)
        limited = items[: self._max_targets]
        points = [(item[2], item[3]) for item in limited]
        confidences = [item[0] for item in limited]
        class_ids = [item[1] for item in limited]
        return points, confidences, class_ids


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


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    dx = ax - bx
    dy = ay - by
    return (dx * dx + dy * dy) ** 0.5
