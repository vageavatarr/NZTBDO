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
If window guard constraints are set and active window/process does not match, runtime auto-pauses and auto-resumes when focus returns.

## Windows Forms UI (Timer + Data + Stop)

```powershell
dotnet run --project apps/windows-forms/NZTBDO.WinForms.csproj -c Release
```

The form includes:
- session timer (`Elapsed`)
- runtime data (`Events`, `Paused Ticks`, `Guard Blocked`, latest `Session`, `Process PID`)
- `Start` button for `run_session`
- `Test Skills` button for combo execution check
- `Stop` button to terminate the active process

Skill test from CLI:

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.skill_test --profile live_farm --repeats 1
```

## Runtime Loop (Headless)

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.runtime_loop
```

Runtime perception settings are configured in `shared/config/thresholds.yaml` under `perception.runtime`.
If `ultralytics` is available and `model_path` exists, YOLO backend is used; otherwise fallback stub is used.
Runtime perception includes a tracking layer for stable target IDs across frames (`avg_tracks_per_tick` in runtime summary).
Keyboard actions (`press_1..4`) are now logged as `keyboard_action` events in `events.jsonl` (including blocked/rate-limited attempts).
Low-level key telemetry (`down`/`up`) is written to `data/raw/<session_id>/chunk_*.jsonl`.
Screenshot capture starts on the first unpaused tick with allowed game window; this is marked by `capture_started` in `events.jsonl`.

Model readiness preflight:

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.model_preflight --profile live_farm
```

Threshold patch suggestion from latest calibration report (does not modify files):

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.suggest_threshold_patch --profile live_farm --write-patch ../../data/logs/latest_thresholds_suggestion.patch
```

Roadmap milestone status check (Perception v1 + long-run validation):

```powershell
cd services/orchestrator
$env:PYTHONPATH='src'
python -m nztbdo_orchestrator.milestone_status
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

To give yourself time to focus the game window before runtime starts:

```powershell
python -m nztbdo_orchestrator.run_session --profile live_farm --ticks 300 --tick-sleep 0.05 --start-delay 5
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
- `input_control.require_foreground_window: false` to allow background/minimized window binding
- `input_control.bind_to_process: true` to bind by process/window even when not active
- `input_control.allow_background_input: true` to use background window message injection (best-effort)

For live profile, update placeholders in `shared/config/thresholds_live_farm.yaml`:
- `allowed_window_titles: ["GameWindow"]`
- `allowed_process_names: ["game.exe"]`

Current combo actions supported by executor:
- `press_shift_q`
- `press_hold_q_4s` (hold 4.0s)
- `press_shift_rmb_hold` (2.5s hold)
- `press_shift_lmb`
- `press_shift_f`
- `press_s_lmb`

## Capture Demo (Chunked Telemetry)

```powershell
cd services/capture
$env:PYTHONPATH='src'
python -m nztbdo_capture.demo_capture
```

Screen capture is taken from the primary monitor only.
