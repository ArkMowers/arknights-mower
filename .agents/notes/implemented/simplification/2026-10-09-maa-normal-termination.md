---
title: MAA Normal Long-Task Termination
status: implemented
category: simplification
date: 2026-10-09
---

# MAA Normal Long-Task Termination

[中文](2026-10-09-maa-normal-termination.zh.md)

**[INV-MAA-07] Normal Long-Task Termination**: Roguelike, SSSCopilot and Reclamation completion or scheduler interruption never creates an error solely because `running()` returns false; core error callbacks and invocation exceptions retain their error reporting.

`BaseSchedulerSolver.maa_plan_solver` owns the only `maa_crash` flag and the generic long-task interruption error. A false running state carries no failure reason and also follows normal completion. Removing the flag and its error branch eliminates five lines and the redundant ERROR notification, whose logging repeats the same error and whose delivery can send mail. No caller or external interface consumes this flag.

The [MAA integration contract](../../../../docs/subsystems/maa-integration.md) owns termination reporting. Callback translation retains completion, stop and core error messages. Invocation exceptions retain the existing error notification. Scene reset, task deadlines, stop requests, theme restoration and the idle handoff retain their existing behavior.

`maa_error_no_exit_tests.py` covers immediate completion without an error, retry or game exit and preserves invocation-failure notifications. `maa_scene_handoff_tests.py` covers a running task that ends or is stopped by scheduling, with fresh scene state and no added error. Callback tests cover core error severity.

## Standards Findings

Pass: deleting local crash inference reuses callback reporting without adding state, wrappers or configuration. Domain definitions and resource lifecycles remain unchanged.

## Spec Findings

Pass: normal long-task termination produces no generic error or ERROR notification; actual callback and invocation failures retain their reporting.
