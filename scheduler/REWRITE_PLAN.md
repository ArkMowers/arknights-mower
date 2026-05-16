# Rewrite Plan: scene-driven only

## Priority 1 — Must rewrite pattern (not scene-driven)

| File | Problem | Fix |
|------|---------|-----|
| `infra/agent_selection.py` | `ASState` enum + `_handlers` dispatch + interior `while True` tap loops | Rewrite to `while True: scene = get_scene() ...`, each iteration taps once |
| `executors/infra_scan.py` | No state machine, sequential code | Wrap in `while True: scene = get_scene() ...` |

## Priority 2 — Fix violations in partially-migrated executors

| File | Problem | Fix |
|------|---------|-----|
| `executors/workshop.py` | Uses old `Recognizer` directly, not Navigator's scene | Port to `get_scene()` from new Scene enum |

## Priority 3 — Kill all `time.sleep()` (24 violations)

All in `infra/agent_selection.py` and `navigator.py`. Replace with `wait_scene_stable()` or `PauseController.wait_if_paused()`.

## Priority 4 — Eliminate hardcoded values

- `infra/agent_selection.py:52-61` pixel positions → `constants.py`
- `infra/agent_selection.py:66` threshold → `constants.py`
- `infra/agent_selection.py:390,662,704` hardcoded taps → `TapPosition` or `constants.py`
- `infra/room_reader.py:27-28` pixel crops → `constants.py`
- `state.py:15,169,496-518` operator names → config or constants
- `planners/exhaust.py:8` + `planners/order.py:8` duplicated → `constants.py`

## Priority 5 — Housekeeping

- `state.py` 534 lines → split (< 300 limit)
- `safe_execute()` is dead code → either remove or wire into `MainLoop`
- `infra/registry.py` empty class → fill or remove
