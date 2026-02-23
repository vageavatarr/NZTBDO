# NZTBDO

Automation framework for closed-loop farming with combat perception, FSM orchestration, and future AI training.

## Current Bootstrap

- Project structure scaffolded
- Core configs added in `shared/config`
- `combat_state` schema added in `shared/schema`
- Rule-based combat selector added in `services/combat`
- Spatial perception utilities added in `services/perception`
- Loop route runner with stuck detection added in `services/navigation`
- Action executor with rate limiting added in `services/input-control`
- Minimal Python FSM orchestrator integrated with combat/action execution in `services/orchestrator`

## Quick Start (Orchestrator Demo)

```powershell
cd services/orchestrator
python -m nztbdo_orchestrator.main
```

Runtime tick logs are written to `data/logs/<session_id>/events.jsonl`.
Default profile pointer: `shared/config/profiles/default.yaml`.

## Synthetic Loop Run

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.run_loop
```

## Profile Run (Summary + Session Metrics)

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.run_profile --profile default --ticks 600 --tick-sleep 0.05
```

Writes `summary.json` next to session `events.jsonl` in `data/logs/<session_id>/`.

## Auto-Label Latest Session

```powershell
cd services/labeling
$env:PYTHONPATH='src'
python -m nztbdo_labeling.main --logs-root ../../data/logs --labels-root ../../data/labels
```

## Build Training Dataset + Offline Metrics

```powershell
cd services/training
$env:PYTHONPATH='src'
python -m nztbdo_training.main --labels-root ../../data/labels --dataset-file ../../data/processed/dataset_v1.jsonl --metrics-file ../../data/processed/metrics_v1.json
```

## Desktop UI (MVP)

```powershell
python apps/desktop-ui/main.py
```

Controls:
- `F5` start/resume
- `F6` pause
- `F7` stop
- `F12` panic stop

The UI includes a profile selector populated from `shared/config/profiles/*.yaml`.
UI `Start` now runs the runtime pipeline: primary monitor capture -> perception adapter -> orchestrator -> input executor.
If window guard constraints are set and active window/process does not match, runtime auto-pauses.

## Runtime Loop (Headless)

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.runtime_loop
```

Runtime perception settings are configured in `shared/config/thresholds.yaml` under `perception.runtime`.
If `ultralytics` is available and `model_path` exists, YOLO backend is used; otherwise fallback stub is used.
Runtime perception includes a tracking layer for stable target IDs across frames (`avg_tracks_per_tick` in runtime summary).

Model readiness preflight:

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.model_preflight --profile live_farm
```

## Full Session Pipeline (Runtime -> Labeling -> Training)

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.run_session --profile default --ticks 300 --tick-sleep 0.05
```

Live profile run:

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.run_session --profile live_farm --ticks 300 --tick-sleep 0.05
```

Outputs:
- runtime logs: `data/logs/<session_id>/events.jsonl`
- runtime summary: `data/logs/<session_id>/runtime_summary.json`
- session pipeline summary: `data/logs/<session_id>/session_pipeline_summary.json`
- regression report: `data/logs/<session_id>/regression_report.json`
- calibration report: `data/logs/<session_id>/calibration_report.json`
- labels: `data/labels/<session_id>/episodes.jsonl`
- dataset: `data/processed/dataset_v1.jsonl`
- metrics: `data/processed/metrics_v1.json`

## Real Input Mode (Windows)

`services/input-control` now supports real key emission (`1-4`) via `SendInput`.

Configure in `shared/config/thresholds.yaml`:
- `input_control.dry_run: false` to enable real key presses
- `input_control.allowed_window_titles: [...]` to restrict by foreground window title
- `input_control.allowed_process_names: [...]` to restrict by foreground process name

For live profile, update placeholders in `shared/config/thresholds_live_farm.yaml`:
- `allowed_window_titles: ["GameWindow"]`
- `allowed_process_names: ["game.exe"]`

## Capture Demo (Chunked Telemetry)

```powershell
cd services/capture
$env:PYTHONPATH='src'
python -m nztbdo_capture.demo_capture
```

Screen capture is taken from the primary monitor only.
