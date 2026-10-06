---
title: MAA Callback Logging
status: implemented
category: feature
date: 2026-09-30
---

# MAA Callback Logging

[中文](2026-09-30-maa-callback-logging.zh.md)

`arknights_mower/utils/maa_callback.py` translates MAA core callback messages into readable runtime-log lines, and `BaseSchedulerSolver` in `arknights_mower/solvers/base_schedule.py` consumes the translation for every MAA run. The [subsystem specification](../../../../docs/subsystems/maa-integration.md) owns the run boundary and the callback consumption contract.

**[INV-MAA-01] Total Callback Handling**: Every MAA callback is consumed without raising; a missing, empty, or unrecognized payload field yields at most one diagnostic line at the C callback boundary instead of an exception.

**[INV-MAA-02] Callback-Derived MAA Progress**: A MAA run's runtime log derives progress from core callbacks — each task-chain transition and each whitelisted milestone produces one line, while the polling loop contributes at most one heartbeat line per interval.

`parse_details` decodes one callback detail payload; a missing, empty, or unparsable payload yields `{}` instead of raising inside the C callback. `MaaCallbackLog.describe` maps one message and payload to a `MaaLogLine(level, text)`, and the caller logs it. Wording and severity follow the MAA desktop client's callback handler, so each event carries the level that client gives it; an ERROR line from the scheduler module also archives screenshots, which is the one side effect of that choice. Translation lives in the tables `TASK_CHAIN_TEXT`, `CONNECTION_TEXT`, `SUB_TASK_INFO`, `PROCESS_TASK_START`, `PROCESS_TASK_COMPLETED`, `SUB_TASK_ERROR` and `REPORT_WHY_TEXT`, covering the task chains this scheduler submits — StartUp, Fight, Mall, Award, Recruit, Roguelike, SSSCopilot, Reclamation and SwitchTheme — plus other known chains. Table lookups normalize their key to a string, and payload fields of an unexpected type degrade to a default conclusion, so no field shape reaches the tables unguarded.

Filtering keeps recurring telemetry (`EmulatorFPS`, `FastestWayToScreencap`, `MuMuExtrasInputStatus`) and facility traffic at DEBUG. `ScreencapCost` carries no conclusion and produces no line. `ProcessTask` sub-task start and completion lines appear only for a node-name whitelist, which is the MAA client's own anti-spam mechanism; every other node produces no translated line. `SubTaskStopped` (20004) produces no line. `TaskChainStopped` (10004) does, because the loops that stop MAA on purpose do not all record the stop themselves.

`MaaCallbackLog.heartbeat` emits at most one INFO line per `HEARTBEAT_INTERVAL` (60 s), naming the running task chain and the elapsed run time, and appends a stall note when no callback has arrived for `STALL_AFTER` (180 s). Construction takes injectable `interval`, `stall_after` and `clock` (default `time.monotonic`); the tests inject a fake clock. The task chain clears when a chain completes (10002), stops (10004) or when all tasks complete (3), so neither a finished nor a stopped chain appears as running.

`initialize_maa` assigns a fresh `MaaCallbackLog` per MAA run on both the desktop and the `MOWER_ANDROID` path, before the verified `Asst` construction and its connect call, so connection callbacks are covered. `on_maa_callback` is the callback entry point: it decodes the payload, keeps accumulating well-formed `StageDrops` into the module-level `stage_drop` for the existing `maa_stop` report, and logs the translated line at its severity through the scheduler module's logger. `reset_stage_drop` owns the per-run reset that `maa_plan_solver` and `maa_stop` share. `report_maa_progress` calls `heartbeat()` and logs only when the interval has elapsed. Both MAA polling loops replace the per-5-second `logger.info("MAA 运行中...")` line with `self.report_maa_progress()`.

The previous callback was a class-level `@CFUNCTYPE` method named `log_maa` whose three `Recruit*` branches wrote the module globals `recruit_tags_selected`, `recruit_special_tags` and `recruit_results`. No module in the repository defines those names, so the branches raised `NameError` inside the ctypes callback and ctypes swallowed it. Nothing consumes that state, and translated log lines replace the branches. The unused `Message` import and global, the unused `ctypes` and `json` imports, and the matching `maa_update.clear_loaded_maa_cache` nulling of that global leave the module together. The method takes its current name because it also serves the delegated report upload; the [report upload decision](2026-10-01-maa-report-upload.md) covers that contract.

`arknights_mower/tests/maa_callback_tests.py` holds 59 hermetic tests over an injected fake clock: payload decoding, wrong-typed payload fields across every known `what` and message code, non-string operator names, the message families, the noise filters, heartbeat throttling and stall text, the malformed-drop accumulator, the per-run drop reset, and the scheduler wiring, including `VerifiedAsst` callback routing and `initialize_maa` creating a fresh reporter. Existing suites `maa_error_no_exit_tests.py`, `maa_backup_tests.py`, `maa_restore_theme_tests.py`, `maa_scene_handoff_tests.py`, `maa_check_tests.py`, `base_scheduler_tests.py`, `maa_update_tests.py` and `stage_plan_scheduler_tests.py` still pass.

`ReportRequest` (30000) carried no readable progress line, so this change records its payload at DEBUG and leaves the request itself to the upload path described in the [report upload decision](2026-10-01-maa-report-upload.md). This host's own `runtime.log` recorded the core handing over a prepared request naming `https://penguin-stats.io/PenguinStats/api/v2/report` with `subtask` `ReportToPenguinStats`, which is the evidence that core delegates the POST rather than performing it.

Interface evidence: [MAA callback protocol](https://docs.maa.plus/zh-cn/protocol/callback-schema.html) and [MAA desktop client callback handler](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/dev-v2/src/MaaWpfGui/Main/AsstProxy.cs).

## Standards Findings

Pass: the reporter logs through the scheduler module's logger, so MAA lines retain the runtime log policy of the module that owns the run. Payload decoding replaces exceptions with an empty mapping at the C callback boundary, and every table lookup normalizes its key, so no field shape reaches a table unguarded. The removed `Recruit*` branches end writes to undefined module globals, and the unused `Message`, `ctypes` and `json` bindings leave with them, including the `maa_update` cache release that nulled `Message`. Recurring telemetry stays at DEBUG or produces no line, and heartbeat emission is bounded by an injectable interval rather than by polling frequency. No Device Profile, Scheduling Plan or glossary definition changes; `CONTEXT.md` and `CONTEXT.zh.md` remain untouched.

## Spec Findings

Pass: every callback path in `describe` returns a line or `None` without raising, and `parse_details` covers missing, empty and unparsable payloads. Translation covers the task chains this scheduler submits, with wording drawn from the MAA client and severity chosen for this runtime log. Filtering matches the stated policy: `ScreencapCost` and `SubTaskStopped` produce no line, other telemetry and facility traffic sit at DEBUG, and `ProcessTask` start and completion emit only for the whitelist. Heartbeat throttling, stall text and task-chain clearing match [INV-MAA-02], which includes the stop path. Scheduler wiring covers both MAA run paths in `initialize_maa`, both polling loops, and `StageDrops` accumulation for the `maa_stop` report. Offline tests cover every boundary above; live MAA runs stay outside these tests.
