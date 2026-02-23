from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SRC = ROOT / "services" / "capture" / "src"
if str(CAPTURE_SRC) not in sys.path:
    sys.path.insert(0, str(CAPTURE_SRC))

from nztbdo_capture.chunked_writer import ChunkedJsonlWriter


def test_chunk_rotation(tmp_path: Path) -> None:
    writer = ChunkedJsonlWriter(tmp_path, chunk_size=3)
    for idx in range(7):
        writer.write({"i": idx})
    writer.close()

    files = sorted(tmp_path.glob("chunk_*.jsonl"))
    assert len(files) == 3
