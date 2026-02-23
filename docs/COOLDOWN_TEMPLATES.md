# Cooldown Icon Templates (Live Farm)

This document fixes the primary cooldown icon templates for combo learning.

Config source:
- `shared/config/cooldown_templates_live_farm.yaml`

User-fixed template order:
1. `icon_01` -> `press_shift_q`
2. `icon_02` -> `press_hold_q_4s`
3. `icon_03` -> `press_shift_rmb_hold`
4. `icon_04` -> `press_shift_lmb`
5. `icon_05` -> `press_shift_f`
6. `icon_06` -> `press_s_lmb`
7. `icon_07` -> `press_lmb`

Training target labels:
- `cooldown_state`: `ready | cooling`
- `cooldown_seconds`: continuous regression target

Notes:
- `press_s_lmb` and `press_lmb` are explicitly distinct actions and must remain separated in labeling/training.
- Template ROI is defined in config and will be calibrated on real sessions.
