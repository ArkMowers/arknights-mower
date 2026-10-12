---
format: decision
authors: [Codex]
title: Owned Instance Supervision
status: implemented
category: architecture
date: 2026-10-12
---

# Owned Instance Supervision

[中文](2026-10-12-owned-instance-supervision.zh.md)

## Problem

A native main-process exit bypasses Python task recovery, and a surviving HTTP service cannot repair an exited automation worker by itself. Recovery must preserve explicit Stop, configuration-space ownership and the existing high-level task and compensation boundaries.

## Decision

The Windows desktop launcher separates instance supervision from the Python process that owns HTTP and device dispatch. The supervisor imports lightweight runtime coordination, retains exclusive ownership of one configuration space, and detects process termination and sustained HTTP unavailability. Bounded cooldowns keep recovery available after the initial fast attempts. Intentional closure, update and explicit process replacement end the old supervisor instead of competing with the replacement.

The [process recovery contract](../../../../docs/subsystems/process-recovery.md) owns the complete launch, intent, retry and observation boundary. Existing device recovery retains pending task preservation and uncertain input delivery rules. The implementation reuses saved-state startup, SQLite checkpoints, high-level task solvers, inventory invalidation and desktop parent watching. It adds neither a separate scheduling engine nor a new runtime dependency.

## Recovery

The supervisor restores service after a native main-process failure. A persistent recovery controller also admits ordinary Python worker failures. Both preserve task-run intent and continue after temporary startup, snapshot or observation failures. Recovery automatically observes actual room occupancy, mood and relevant task state, saves a checkpoint, then returns to existing solver recovery. Ordinary Stop cancels that intent; an accepted ordinary Start enables it again. No separate acknowledgement, manual completed-task disposition or new action-receipt system is required.

Due dynamic trade orders and Fiammetta charging need replanning because the interrupted effect can already have completed. Existing task types provide that reentry, while saved roster compensation and future appointments remain available. Existing Workshop stock records become unverified until depot observation supplies required counts; this delays crafting while other scheduling continues. Quiet logs during a healthy service do not establish a hang. This boundary does not establish exactly-once irreversible actions, reconstruct a roster held only on the interrupted Python stack or repair a confirmed invalid configuration.

Instance Binding, Capture Frame and Scheduling Plan retain their meanings. Runtime supervision files remain separate from user configuration; concept-impact review requires no glossary change. The independent process ownership rule is named in the process recovery subsystem.

## Alternatives considered

WinSW manages Windows services and failure restarts, but a service deployment changes desktop session, GUI and installation assumptions and still needs Mower task intent, HTTP health and state reconciliation. Pebble and loky manage process tasks rather than a complete desktop instance. The selected supervisor retains the desktop entry and existing update and process replacement coordination.

## Consequences

Unexpected exits and sustained HTTP unavailability receive continuing attempts; recovery waits for fresh observations and checkpointing rather than replaying uncertain input. The supervisor has its own memory cost and does not establish scheduler progress while HTTP remains healthy. Durable user reset or queue-clear choices remain active through failed recovery attempts; a successful new checkpoint replaces the original SQLite snapshot.

## Verification Status

Initial focused Windows [instance supervision](../../../../arknights_mower/tests/instance_supervisor_tests.py), [process-crash recovery](../../../../arknights_mower/tests/process_crash_recovery_tests.py) and [automatic recovery](../../../../arknights_mower/tests/automatic_process_recovery_tests.py) suites passed 72 cases, exercising real temporary interpreter exits, continuing cooldowns, process-creation failure, HTTP availability, Job membership, foreign-PID rejection, wrapper-first exits, surviving-child exclusivity, replacement ownership release and Stop under report-write failure. Production worker and scheduler-entry checks cover ordinary exceptions, internal fatal shutdown, cancellation, strict room observation, malformed SQLite data and real SQLite checkpoint roundtrips preserving tasks and compensation. Dynamic order, Fiammetta and inventory tests exercise existing reentry paths. Existing [device recovery supervision](../../../../arknights_mower/tests/device_recovery_supervision_tests.py) and [idle scene watchdog](../../../../arknights_mower/tests/idle_scene_watchdog_tests.py) suites pass 37 compatibility cases, including observed recovery and cancellation after uncertain input.

The [desktop parent-death tests](../../../../arknights_mower/tests/desktop_parent_death_tests.py) pass three cases using the real splash, tray and window process creation path with offline waiting targets. Before the parent watcher repair, all three synthetic helpers survive main-process termination; afterward all three exit. The [copied-updater entry test](../../../../arknights_mower/tests/supervisor_deployment_tests.py) passes one case using only the four existing copied standard-library modules while blocking checkout imports; ownership waiting remains available during detached source installation. Existing [process control tests](../../../../arknights_mower/tests/process_control_tests.py) cover explicit replacement and preservation of other instances.

After rebase and startup-mode repairs, the combined focused screenshot, recovery, desktop, process-control, status and scheduled-start suites pass 285 tests and 88 subtests; 22 frontend tests also pass. New regressions reach the real HTTP start route and SQLite snapshot, preserve modes `0`, `1` and `2`, bypass a damaged snapshot for an explicit reset, retain that reset through observation failure and main-process restart, and return later independent failures to ordinary recovery.

The 2026-10-13 review rebases the work onto alpha commit `52dba896f`. In the existing isolated Windows environment with OpenCV 4.11.0.86, NumPy 1.26.4 and Pillow 10.3.0, the focused screenshot, recovery, desktop, process-control, status, scheduled-start and update suites pass 408 tests and 326 subtests in 86.74 seconds. Three POSIX or macOS cases are skipped; the three frontend suites pass 22 tests. Review repairs explicitly write two generated Python scripts as UTF-8 for Chinese temporary paths and update the existing desktop update-start assertions to require automatic admission. The initial script encoding failure and stale assertions are reproduced before repair. Python lint and format checks pass separately.

Source and frozen argument construction and early worker dispatch are checked. Full frozen-package installation and live-device endurance remain outside this verification. No live device or existing instance participates in these checks.

## Resource Measurement

A same-host source-environment comparison uses one read-only 1920×1080 game screenshot in three rounds. Each channel receives 31 frames. The previous two-slot implementation is loaded from the pre-rebase stash for the comparison; both versions use the current Pillow codec and process owner. Every phase includes the same loaded supervisor modules, owned Job and actual loopback HTTP probe, the live encoding process groups including launcher descendants, and measured parent-control private-memory delta.

| Phase | Encoding children | Median additional private commit |
| --- | ---: | ---: |
| Previous two-slot implementation | 2 | 55.1 MiB |
| Primary shared by sequential history and preview | 1 | 37.7 MiB |
| Primary busy, auxiliary encoding previews | 2 | 55.3 MiB |
| Auxiliary reclaimed after default idle timeout | 1 | 37.6 MiB |

The loaded supervisor group uses 20.2 MiB. Reclamation completes 30.5–30.6 seconds after the last auxiliary frame while the primary continues encoding. The one-child idle phase saves approximately 17.5 MiB, about 32% of this additional private commit. Contentious work still uses two children and has comparable warm memory to the previous implementation. Every probe child is reaped before temporary ownership files are removed.

One live child has 13.8 MiB of fixed file-backed mapping capacity; two have 27.7 MiB. This capacity is reported separately and is not added to private commit. Windows private commit is not physical resident memory, and a warm two-child observation is not a simultaneous peak-memory measurement. Source measurements do not establish frozen-program memory use or continuous-run stability. [Screenshot encoding evidence](2026-10-12-isolated-screenshot-encoding.md#performance-evidence) retains the earlier codec and IPC timings; an auxiliary restarted after reclamation pays process creation again.
