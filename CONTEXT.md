# NZTBDO - Detailed Project Context

## 1. Business Goal

Build a practical automation assistant for repetitive game farming loops with:
- closed patrol trajectory,
- combat execution against aggressive monsters,
- continuous loop farming after respawn cycles,
- multimodal data capture for later auto-labeling and model training,
- simple desktop UI with hotkeys for operator control.

Core value: stable runtime behavior first, AI improvement second.

## 2. Confirmed Functional Requirements

1. Agent follows a closed route and repeats it continuously.
2. Monster spawn positions vary slightly each loop.
3. Monsters are aggressive and move/attack with non-deterministic patterns.
4. Agent must:
- detect monsters,
- understand relative positions,
- count enemies near and specifically in front,
- conduct combat,
- resume movement after combat clears.
5. Skills are on keys `1-4`.
6. Skills have cooldowns and must be used with cooldown awareness.
7. Loot handling is out of scope (auto-loot exists in game).
8. Final product needs a simple visual interface with hotkeys.

## 3. Operating Assumptions

1. Runtime control loop must be low-latency and deterministic.
2. LLM/VLM should be used mainly offline (labeling, analysis), not for per-frame combat decisions.
3. Safety controls are mandatory (panic stop, pause, allowlist window checks).
4. Configuration-first design is needed to tune per class/zone without code edits.

## 4. Recommended System Strategy

Hybrid approach:
- realtime layer: CV perception + finite-state machine + rule-based combat logic,
- data layer: rich telemetry and episode storage,
- learning layer: auto-label episodes and train policy to improve decisions over time.

Reason: this balances reliability (short-term) and adaptability (long-term).

## 5. Architecture (Service Boundaries)

1. `capture`:
- screen frames,
- input events (keyboard/mouse),
- active window metadata,
- timestamp synchronization.

2. `perception`:
- enemy detection,
- enemy tracking (stable IDs),
- spatial relation features (front/near/left/right/back),
- confidence outputs.

3. `navigation`:
- waypoint/spline loop execution,
- route progress tracking,
- stuck detection and recovery actions.

4. `combat`:
- target selection,
- skill scheduler (`1-4`) with cooldown constraints,
- simple repositioning logic.

5. `input-control`:
- safe key/mouse sender,
- rate limiting,
- hard panic override.

6. `orchestrator`:
- global FSM state transitions,
- per-tick feature aggregation,
- action arbitration.

7. `labeling`:
- auto-labeling of episodes via VLM/LLM,
- confidence scoring,
- low-confidence routing for review.

8. `training`:
- dataset building,
- imitation/hybrid policy training,
- offline evaluation/regression gating.

9. `desktop-ui`:
- start/pause/stop/panic hotkeys,
- profile management,
- live status and logs.

## 6. Runtime Decision Model

Global FSM states:
- `IDLE`
- `PATROL`
- `ENGAGE_CHECK`
- `COMBAT`
- `POST_COMBAT`
- `RECOVERY`
- `PAUSED`
- `PANIC_STOP`

Core transitions:
- Patrol to combat when enemy confidence threshold is met.
- Combat to patrol when area is clear for a configurable time.
- Any state to recovery on stall/invalid progress.
- Any state to panic on emergency hotkey.

## 7. Combat State Semantics

Per-tick features (minimum):
- `enemies_total_near`
- `enemies_in_front`
- `nearest_enemy_dist`
- `target_id`
- `skill_cd[1..4]`
- `time_since_last_kill`
- `in_combat`

Skill selection priority (initial):
1. front-AOE when front count threshold met,
2. around-AOE when near count threshold met,
3. highest-priority single-target skill ready,
4. filler/reposition while waiting for cooldowns.

Safety fallback:
- if no effective progress for timeout window, force `RECOVERY`.

## 8. Route and Respawn Loop Behavior

1. Patrol loop runs continuously.
2. Combat interrupts route progression but does not discard route context.
3. After clear, nearest forward route point is reacquired.
4. By the time loop returns to prior areas, monsters are expected respawned.
5. This creates stable cyclical farming behavior.

## 9. Data Capture and Learning Context

Why multimodal capture:
- enables forensic debugging,
- supports auto-labeling quality,
- allows model improvement from real runs.

Recommended storage:
- raw events in JSONL chunks,
- training-ready tables in Parquet,
- metadata index in SQLite/DuckDB.

Critical logged fields:
- timestamp, FSM state, perception features, action, confidence, latency, outcome.

## 10. Auto-Labeling Context

Auto-labeling should classify:
- tactical context (enemy distribution),
- action rationale category (front AOE / around AOE / single / reposition / wait),
- outcome quality (effective/ineffective/neutral).

Two-pass cost strategy:
- fast model for broad pass,
- stronger model for uncertain segments only.

## 11. UI and Operator Flow

Minimum interface requirements:
- run controls,
- hotkeys,
- current state and target counters,
- health/status alerts,
- quick access to session logs.

Suggested hotkeys:
- `F5` start/resume,
- `F6` pause,
- `F7` stop,
- `F12` panic.

## 12. Non-Functional Constraints

1. Decision latency budget should remain bounded (target low tens of ms per tick).
2. System must run for long loops without deadlock.
3. Panic stop must be immediate and reliable.
4. Observability must support post-session diagnosis.

## 13. Delivery Direction (Already Prepared)

A detailed implementation roadmap has been saved in:
- `ROADMAP.md`

It includes:
- phased delivery plan,
- acceptance criteria by phase,
- KPIs,
- test strategy,
- immediate next execution tasks.

## 14. Immediate Project Baseline State

Current repository workspace contains:
- `ROADMAP.md` (detailed roadmap),
- `CONTEXT.md` (this preserved requirement and architecture context).

This baseline is ready to be committed as project planning foundation.

## 15. Primary Visual Labeling Rules (User-Confirmed)

These rules are required for initial supervised labeling:

1. Aggro indicator:
- Monsters that are engaged/aggroed are marked by a yellow exclamation sign above them.
- Presence of yellow exclamation marks should be treated as high-priority aggro signal for combat entry.

2. Player anchor:
- Controlled character is expected near screen center.
- Character identity can be stabilized by two bars above the character head (HP/resource bars).
- This anchor should be used for relative enemy geometry features (`front`, `near`, `left`, `right`).

3. First-pass annotation implication:
- For each frame/tick, count:
  - enemies with yellow exclamation marks near player,
  - enemies with yellow exclamation marks in front cone.
- Use these counts as primary labels for early combat policy data.

4. Orientation source for navigation/combat geometry:
- Minimap is located at the top-right area of the screen.
- Camera direction is represented around the player marker on the minimap.
- For heading-dependent features, prefer camera/minimap heading over character body orientation.
- Character model may rotate independently while moving and does not reliably encode global heading.

5. Combat combo profile (`bdo_combo_v1`):
- `Shift+Q+Q`: AOE around character, cooldown 10s.
- `Shift+RMB` hold 2.5s: short-range frontal double hit, cooldown 8s.
- `Shift+LMB`: short-range frontal hit, cooldown 7s.
- `Shift+F`: long-range frontal hit, cooldown 8s.
- `S+LMB`: short-range finisher, no cooldown, very small radius (1-2 targets).

6. Enemy visual signature (primary farm target):
- Humanoid, pale/stone-like body and armor silhouette.
- Large melee weapon is frequently visible.
- Yellow exclamation mark above head is the strongest aggro/engaged marker.
- In dense foliage/partial occlusion, exclamation mark should be prioritized over full-body visibility.
