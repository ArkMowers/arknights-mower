---
title: Idle Resumption Preserves Scene Watchdog
status: implemented
category: bug-fix
date: 2026-10-08
---

# Idle Resumption Preserves Scene Watchdog

## Scope

**[INV-REC-08] Idle Observation Boundary**: Successful scheduler idle resumption discards cached Capture Frames and scene state and restarts continuous scene and loading observation, excluding idle time from scene timeout while routine capture refresh and active observation retain freeze detection.

The [Base Scheduling Contract](../../../../docs/subsystems/base-scheduler.md) owns this boundary. Device identity, shutdown consent and recovery budgets retain their existing contracts.

## Evidence

The [captured evidence](../../../../arknights_mower/tests/fixtures/scheduler_incident_20261008.json) identifies the following runtime events:

| Time | Observation |
| --- | --- |
| 10:55:38.643 | Scheduler waits 298.417708 seconds for the next task. |
| 10:56:15.034 | A resource update completes during the idle interval. |
| 11:00:37.237 | The first resumed observation identifies INFRA_MAIN. |
| 11:00:37.239 | `Recognizer.check_freeze` reports scene timeout and exits the game. |

The captured configuration sets `run_order_delay` to 3 minutes. `check_freeze` uses `run_order_delay * 90`, a 270-second threshold. The legitimate idle interval alone exceeds that threshold.

## Cause

On captured baseline `87b9d3aa`, [`_idle_sleep`](../../../../arknights_mower/solvers/base_schedule.py) ends with `recog.update()`. [`Recognizer.update`](../../../../arknights_mower/utils/recognize.py) invalidates the Capture Frame and cached scene but preserves `last_scene` and `last_scene_time`. Recognition of the same scene after intentional idle therefore counts the unobserved interval as continuous scene residence.

On that baseline, `rest_until_next_task` resets `last_scene` before its wait. The wait inside `BaseSchedulerSolver.run` calls `_idle_sleep` directly and receives no equivalent reset. The logged warning originates from `check_freeze`, rather than a loading-scene wait. The offline failure also occurs with resource refresh replaced by a no-op.

## Implementation Boundary

`_idle_sleep` calls the existing `Recognizer.reset_after_external_control` on successful resumption. That operation invalidates the cached Capture Frame and scene, clears `last_scene`, starts a new observation timestamp and resets loading observations. The next recognition obtains a fresh Capture Frame. If simulator startup or reconnect fails after waiting, the observation boundary remains pending; [`_resume_device_dispatch`](../../../../arknights_mower/__main__.py) completes the reset only after device recovery succeeds. HTTP wakeup, maintenance waiting, simulator recovery and the `sleeping` lifecycle retain their existing order. Stop and recovery errors propagate before recognition resumes.

Four production waiting entries share `_idle_sleep`: `BaseSchedulerSolver.run`, `rest_until_next_task`, MAA error handling and `__main__._handle_maintenance`. The shared boundary reuses the recognition reset and removes the redundant `last_scene` assignment in `rest_until_next_task`; it adds no wrapper or new recognition API. Routine `Recognizer.update`, `BaseSolver.sleep` and active device recovery continue to preserve the scene watchdog. The repair uses the existing Capture Frame and scheduling concepts.

## Verification

The [incident replay](../../../../arknights_mower/tests/scheduler_incident_20261008_tests.py) executes the real `_idle_sleep` and `check_freeze` with a fixed clock. The original regression receives one erroneous game exit before the repair and no exit after it.

The [idle observation tests](../../../../arknights_mower/tests/idle_scene_watchdog_tests.py) execute production recognition and lazy capture against simulated Capture Frames after normal deadline, early wake and maintenance waits. Resumption excludes the 298.417708-second idle interval. At exactly 270 seconds of active observation the watchdog permits the scene; at 271 seconds it exits the game, including after `Recognizer.update` and `BaseSolver.sleep` refreshes.

The same tests execute `rest_until_next_task` and `__main__._handle_maintenance` through a 600-second wait, failed startup or reconnect, `_resume_device_dispatch` and `BaseSchedulerSolver.run`. The first production observation captures a fresh frame without exiting the game. Failed recovery attempts and cancellation leave recognition untouched until successful device recovery. A subsequent active recovery preserves the observation timestamp. On review commit `f2a99d312c1a714384a12473a05b68761a6e82ca`, these new cases produce five failures; with the pending boundary repair, all eleven idle observation cases pass.

Existing simulator lifecycle, MAA handoff and [device recovery supervision tests](../../../../arknights_mower/tests/device_recovery_supervision_tests.py) cover recovery ordering, ordinary capture refresh, finite retry budgets and stop propagation.

```text
python -m pytest arknights_mower/tests/scheduler_incident_20261008_tests.py -k 'idle or scheduler_sleep' -q
python -m pytest arknights_mower/tests/idle_scene_watchdog_tests.py arknights_mower/tests/maa_scene_handoff_tests.py -q
python -m pytest arknights_mower/tests/base_scheduler_tests.py -k 'TestIdleSimulatorWake or idle_sleep_wakes' -q
```
