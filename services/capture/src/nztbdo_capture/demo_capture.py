from __future__ import annotations

from pathlib import Path

from nztbdo_capture.input_recorder import InputTelemetryRecorder
from nztbdo_capture.screen_capture import PrimaryMonitorCapture


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    out_dir = root / "data" / "raw" / "demo_capture"
    frames_dir = out_dir / "frames"
    recorder = InputTelemetryRecorder(str(out_dir), chunk_size=5)
    capturer: PrimaryMonitorCapture | None = None
    capture_ready = True

    try:
        capturer = PrimaryMonitorCapture()
    except RuntimeError as exc:
        capture_ready = False
        print(f"screen_capture_disabled={exc}")

    for idx in range(12):
        recorder.record_window(
            title="GameWindow",
            process="game.exe",
            rect={"x": 100, "y": 100, "w": 1280, "h": 720},
        )
        recorder.record_keyboard(key=str((idx % 4) + 1), event_type="down")
        recorder.record_mouse(x=600 + idx, y=400 + idx, button="left", event_type="move")
        if capture_ready and capturer is not None:
            frame = capturer.capture_to_png(frames_dir=frames_dir, prefix="frame", index=idx)
            recorder.record_frame_meta(
                frame_id=frame.frame_id,
                width=frame.width,
                height=frame.height,
                path=frame.path,
            )
        else:
            recorder.record_frame_meta(
                frame_id=f"frame_{idx:04d}",
                width=1280,
                height=720,
                path=f"frames/frame_{idx:04d}.png",
            )

    if capturer is not None:
        capturer.close()
    recorder.close()
    print(f"capture_written={out_dir}")


if __name__ == "__main__":
    main()
