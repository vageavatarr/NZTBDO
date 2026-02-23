# NZTBDO - Detailed Roadmap

## 1) Context Summary and Target Result

Project goal: build an AI-assisted game automation system that:
- runs on a closed trajectory (loop route),
- detects monsters and their relative positions,
- counts enemies near and in front,
- chooses and uses skills on keys `1-4` with cooldown awareness,
- continues route after combat,
- repeats farm loop when monsters respawn,
- does not process loot logic (auto-loot in game),
- provides a simple desktop UI with hotkeys.

Recommended implementation strategy:
- deterministic core for realtime control (perception + FSM + rules),
- data logging for every decision,
- auto-labeling pipeline (VLM/LLM) for offline improvement,
- gradual migration from rules to learned policy where it adds value.

---

## 2) Product Scope

### In Scope (v1-v2)
- Screen-based perception (computer vision).
- Keyboard/mouse control.
- Route following on loop.
- Combat loop with target/skill selection.
- Cooldown management.
- Safety controls (panic hotkey, pause, stop).
- Logging and replay.
- Auto-labeling of episodes for dataset growth.

### Out of Scope (initially)
- Full autonomous questing.
- Loot prioritization (explicitly not needed).
- Economy systems (market, inventory optimization).
- Anti-cheat evasion research.

---

## 3) High-Level Architecture

Monorepo layout:

```text
NZTBDO/
  apps/
    desktop-ui/                 # Start/pause/stop, profile select, status, logs
  services/
    capture/                    # Frame capture + keyboard/mouse event stream
    perception/                 # Enemy detection/tracking + combat spatial features
    navigation/                 # Loop trajectory, waypoint logic, stuck recovery
    combat/                     # Target selection, skill scheduler (1-4), positioning
    input-control/              # Safe key/mouse sender with guardrails
    orchestrator/               # Global FSM and tick loop
    labeling/                   # Offline auto-labeling with VLM/LLM
    training/                   # Dataset build, model training, evaluation
  shared/
    schema/                     # JSON schema/pydantic models for events/states
    config/                     # skills.yaml, route.yaml, thresholds.yaml
  data/
    raw/                        # Captured chunks
    processed/                  # Cleaned + aligned datasets
    labels/                     # Auto-label outputs
    models/                     # Trained artifacts
    logs/                       # Runtime logs and metrics
  docs/
    ROADMAP.md
    ARCHITECTURE.md
    OPERATIONS.md
```

Language split:
- Python: perception, orchestration, labeling, training.
- TypeScript + Tauri: desktop UI + hotkeys.
- Optional Rust module: high-performance capture/input if Python path is unstable.

---

## 4) Runtime Control Model

### Global FSM
States:
1. `IDLE`
2. `PATROL`
3. `ENGAGE_CHECK`
4. `COMBAT`
5. `POST_COMBAT`
6. `RECOVERY`
7. `PAUSED`
8. `PANIC_STOP`

Transitions:
- `IDLE -> PATROL`: user start hotkey.
- `PATROL -> ENGAGE_CHECK`: enemies detected or aggro indicator.
- `ENGAGE_CHECK -> COMBAT`: confidence above threshold.
- `COMBAT -> POST_COMBAT`: no alive enemies for `T_clear`.
- `POST_COMBAT -> PATROL`: route reacquired.
- `ANY -> RECOVERY`: no progress, target lost too long, path mismatch.
- `ANY -> PANIC_STOP`: panic hotkey.
- `ANY -> PAUSED`: pause hotkey.

Main tick rates:
- capture/perception: 15-30 FPS,
- decision tick: 10-20 Hz,
- logging flush: 1 Hz + on critical events.

---

## 5) Combat Intelligence Design

### Perception Features Per Tick
- `enemies_total_near`: enemies within radius `R_near`.
- `enemies_in_front`: enemies inside front cone `(angle, distance)`.
- `enemies_left`, `enemies_right`, `enemies_back`.
- `nearest_enemy_dist`, `nearest_enemy_bearing`.
- `target_id`, `target_confidence`.
- `in_combat` bool.
- `time_since_last_kill`.

### Skill Geometry (`skills.yaml`)
Per skill:
- key: `1|2|3|4`
- kind: `single | cone | circle | line`
- params: `range`, `angle`, `radius`, `width`
- cooldown_sec
- min_targets
- priority
- optional: opener/finisher tag

### Decision Priority (initial rules)
1. Use frontal AOE if `enemies_in_front >= min_targets`.
2. Else use around AOE if `enemies_total_near >= min_targets`.
3. Else use highest-priority single-target ready skill.
4. If all on cooldown, do filler/basic attack or short reposition.
5. Hard timeout fallback: if no kill/progress for `T_timeout`, switch to `RECOVERY`.

### Cooldown Tracking
- Preferred: read cooldown from screen UI (icon state/OCR/brightness classifier).
- Backup: local timer model after successful key press.
- Use confidence gating: if cooldown uncertain, choose safer alternative.

---

## 6) Navigation on Closed Trajectory

Route representation:
- waypoint graph or spline with ordered loop index.
- each waypoint has tolerance radius and expected heading.

Patrol algorithm:
1. Move toward current waypoint.
2. If within tolerance, advance to next.
3. On combat entry, freeze waypoint progression.
4. On combat end, reacquire nearest forward waypoint.

Recovery logic:
- detect stuck: no coordinate/progress change for `T_stuck`.
- micro-actions: jump/strafe/repath to nearby waypoint.
- escalation ladder:
  1. short repath,
  2. backtrack one waypoint,
  3. route reset to anchor point,
  4. stop bot + alert.

---

## 7) Data and Schema Plan

Storage choices:
- `JSONL` for events (easy debugging).
- `Parquet` for training tables (fast analytics).
- `SQLite`/`DuckDB` for indexing sessions and querying metrics.

Core entities:
1. `Session`
2. `Episode` (time chunk, e.g. 5-15 sec)
3. `FrameRef`
4. `InputEvent`
5. `PerceptionState`
6. `DecisionEvent`
7. `OutcomeEvent`

Minimal event fields:
- `session_id`, `episode_id`, `timestamp_ms`,
- `state` (fsm state),
- `features` (enemy counts, distances, cds),
- `action` (pressed key, movement command),
- `confidence`,
- `latency_ms`,
- `outcome` (hit_count, damage proxy, kill event).

Data quality rules:
- synchronized timestamps across frame/input/action streams,
- monotonic event ordering,
- dropped-frame counters,
- confidence tracked for all model outputs.

---

## 8) Auto-Labeling Strategy

Goal: transform raw episodes into structured training samples.

Pipeline:
1. Chunk raw session into combat/non-combat episodes.
2. Generate candidate labels with fast model pass.
3. Escalate uncertain episodes to stronger VLM/LLM pass.
4. Validate with rule checks (schema + logic consistency).
5. Publish to `data/labels` with confidence score.

Label types:
- tactical context (`front_count`, `near_count`, pressure),
- chosen action reason class (`aoe_front`, `aoe_around`, `single`, `reposition`, `wait_cd`),
- outcome class (`good`, `neutral`, `bad`).

Human review:
- sample low-confidence tails,
- correct labels in lightweight reviewer tool (later phase).

---

## 9) Model Training Roadmap

### Stage A: Rule-Only Baseline
- No policy model.
- Collect high-quality logs from deterministic behavior.
- Build baseline KPIs.

### Stage B: Imitation Learning
- Train action policy from labeled episodes.
- Inputs: compact state vector + optional visual embedding.
- Outputs: action logits (`skill1..4`, move, wait, reposition).

### Stage C: Hybrid Policy
- Use policy suggestions with rule constraints.
- Rules remain final safety layer (hard constraints).

### Stage D: Online Improvement
- Periodic retraining from new sessions.
- Regression gate before rollout.

Evaluation metrics:
- kills/min,
- deaths/hour,
- route uptime (% time on patrol/combat vs stuck),
- skill utilization efficiency,
- decision latency,
- recovery frequency.

---

## 10) UI and Operator Experience

Desktop UI minimal surface:
- start/pause/stop/panic buttons,
- profile selector (`route + skill config`),
- live status panel: current FSM state, enemy counts, current target, cooldowns,
- session timer,
- log stream with warnings.

Hotkeys:
- `F5`: Start/Resume
- `F6`: Pause
- `F7`: Stop
- `F12`: Panic Stop (hard immediate)

Non-functional UX requirements:
- always-on-top optional,
- clear red state indicator on panic/critical failure,
- one-click export logs.

---

## 11) Safety, Compliance, and Risk Controls

Technical safety:
- panic hotkey must bypass all state logic,
- action rate limiter (prevent spam),
- process/window allowlist (only act in target window),
- confidence thresholds before committing risky actions.

Operational risks and mitigations:
1. Detector drift across locations/light effects
   - mitigation: continuous data collection + periodic fine-tuning.
2. Cooldown misread
   - mitigation: dual tracking (vision + timers), conservative fallback.
3. Stuck loops
   - mitigation: multi-level recovery and hard timeout.
4. High latency spikes
   - mitigation: frame skip policy, bounded queue sizes, async pipelines.

---

## 12) Delivery Phases (Detailed)

## Phase 0 - Project Bootstrap (Week 1)
Deliverables:
- repo scaffold,
- coding standards, lint/test setup,
- base configs and env templates,
- simple UI shell with hotkeys and status mock.

Acceptance:
- app launches,
- hotkeys registered,
- start/pause/stop state transitions visible.

## Phase 1 - Capture + Logging Foundation (Week 1-2)
Deliverables:
- screen capture pipeline,
- keyboard/mouse telemetry capture,
- time sync and chunk writer,
- structured logs and session IDs.

Acceptance:
- record 30+ min sessions without crash,
- chunk integrity checks pass,
- replay tool can read session stream.

## Phase 2 - Perception v1 (Week 2-4)
Deliverables:
- enemy detector baseline,
- tracker integration (stable IDs),
- front/near counters and bearings,
- confidence calibration report.

Acceptance:
- stable counts in known farming zones,
- no double-count inflation in basic scenarios,
- latency inside target budget.

## Phase 3 - Navigation Loop + Recovery (Week 3-5)
Deliverables:
- loop route format and loader,
- waypoint runner,
- stuck detector and recovery ladder.

Acceptance:
- 1+ hour patrol with no hard deadlock in test route,
- recovery works on synthetic stuck cases.

## Phase 4 - Combat FSM + Skill Scheduler (Week 4-6)
Deliverables:
- full FSM orchestrator,
- cooldown-aware skill selector for keys `1-4`,
- target and reposition logic,
- post-combat route resume.

Acceptance:
- repeated pull-fight-resume cycles complete reliably,
- skill use follows config and cooldown constraints.

## Phase 5 - End-to-End MVP (Week 6-7)
Deliverables:
- integrated UI + all services,
- profile-based configs (route + skills + thresholds),
- panic and pause hardened.

Acceptance:
- 2-hour unattended loop run with bounded error rate,
- logs complete and diagnosable.

## Phase 6 - Auto-Labeling Pipeline (Week 7-9)
Deliverables:
- episode extraction,
- two-pass auto-labeling,
- schema validation and confidence scoring.

Acceptance:
- labeled dataset generated from MVP sessions,
- low-confidence bucket isolated for review.

## Phase 7 - Policy Training v1 (Week 9-11)
Deliverables:
- baseline imitation model,
- offline evaluator + benchmark suite,
- hybrid inference path (policy + rules).

Acceptance:
- policy improves at least one primary KPI without regressions in safety metrics.

## Phase 8 - Hardening and Ops (Week 11-12)
Deliverables:
- telemetry dashboard,
- regression tests + scenario tests,
- packaging and versioned profiles.

Acceptance:
- reproducible builds,
- rollback-ready release process,
- stable long-run sessions in target environment.

---

## 13) Test Strategy

Test layers:
1. Unit tests
   - cooldown logic, skill selector, geometry overlap.
2. Integration tests
   - FSM transitions, perception-to-decision pipeline.
3. Scenario tests
   - scripted combat scenes with expected actions.
4. Soak tests
   - multi-hour stability on loop route.

Critical assertions:
- never press skill if cooldown predicted active (unless confidence override policy says otherwise),
- panic hotkey always stops control output instantly,
- route progression resumes after combat,
- decisions remain under latency SLO.

---

## 14) Configuration-First Contract

Files to define early:
- `shared/config/skills.yaml`
- `shared/config/route.yaml`
- `shared/config/thresholds.yaml`
- `shared/config/hotkeys.yaml`

Why:
- fast tuning without code changes,
- easier A/B profiles for different classes/zones,
- safer rollout via profile versioning.

---

## 15) KPI Dashboard (What "Good" Looks Like)

Primary KPIs:
- `kills_per_min` (target increasing trend),
- `deaths_per_hour` (target low/stable),
- `patrol_uptime_pct` (target high),
- `combat_resolution_time_sec` (target down),
- `stuck_events_per_hour` (target down),
- `decision_latency_p95_ms` (target under threshold).

Secondary KPIs:
- skill cast effectiveness by key (`1-4`),
- wasted casts rate,
- perception confidence distribution,
- recovery success rate.

---

## 16) Immediate Next Actions (First 5 Work Items)

1. Create repository skeleton from section 3.
2. Define `skills.yaml` and `route.yaml` schema (strict validation).
3. Implement orchestrator skeleton + FSM transitions with mocked perception.
4. Implement capture/logging service and write first session files.
5. Build minimal UI linked to orchestrator (`start/pause/stop/panic`).

Completion criterion for this roadmap step:
- end of Week 2 should already produce playable closed-loop prototype with mocked or basic perception, full logging, and operator controls.

