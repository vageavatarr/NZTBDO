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
