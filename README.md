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

## Real Input Mode (Windows)

`services/input-control` now supports real key emission (`1-4`) via `SendInput`.

Configure in `shared/config/thresholds.yaml`:
- `input_control.dry_run: false` to enable real key presses
- `input_control.allowed_window_titles: [...]` to restrict key emission to target window titles

## Capture Demo (Chunked Telemetry)

```powershell
cd services/capture
$env:PYTHONPATH='src'
python -m nztbdo_capture.demo_capture
```

Screen capture is taken from the primary monitor only.
