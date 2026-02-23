from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ChunkedJsonlWriter:
    """Write JSONL events in bounded chunks to avoid huge single files."""

    def __init__(self, output_dir: str | Path, chunk_size: int = 500) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._chunk_size = max(1, chunk_size)
        self._chunk_index = 0
        self._items_in_chunk = 0
        self._file = self._open_chunk(self._chunk_index)

    def write(self, row: dict[str, Any]) -> None:
        if self._items_in_chunk >= self._chunk_size:
            self._rotate()
        self._file.write(json.dumps(row, ensure_ascii=True) + "\n")
        self._file.flush()
        self._items_in_chunk += 1

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def _rotate(self) -> None:
        self._file.close()
        self._chunk_index += 1
        self._items_in_chunk = 0
        self._file = self._open_chunk(self._chunk_index)

    def _open_chunk(self, idx: int):
        path = self._output_dir / f"chunk_{idx:05d}.jsonl"
        return path.open("w", encoding="utf-8")
