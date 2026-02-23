# NZTBDO Visual Labeling Rules (v1)

## Primary enemy signature

- Enemy type: pale/stone-like humanoid silhouette.
- Often visible with a large melee weapon.
- Yellow exclamation mark above enemy head indicates engaged/aggro state.

## Priority order for detection/labeling

1. Yellow exclamation mark above head.
2. Humanoid body/weapon silhouette.
3. Motion consistency across nearby frames.

## Occlusion handling

- If body is partially hidden by terrain/foliage but yellow exclamation is visible, keep enemy as valid target.
- If both body and exclamation are missing for several frames, degrade confidence gradually instead of instant drop.

## Geometry relation labels

- `near`: enemy inside configured near radius around player anchor.
- `front`: enemy inside front cone based on camera/minimap heading (not character body facing).

## Notes

- Player anchor is near screen center and stabilized by two bars above character.
- These rules are bootstrap priors for first-pass auto-labeling and can be refined after calibration reports.
