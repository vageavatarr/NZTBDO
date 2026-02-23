from __future__ import annotations

from pathlib import Path


class RuntimePerceptionAdapter:
    """
    Lightweight runtime adapter.
    Current implementation is a deterministic frame-hash stub so the end-to-end
    pipeline is wired before a detector model is integrated.
    """

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
