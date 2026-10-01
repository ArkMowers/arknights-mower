---
title: Backup Validation Covers Shift Projection
status: implemented
category: bug-fix
date: 2026-10-02
---

# Backup Validation Covers Shift Projection

[English](2026-10-02-backup-validation-coverage.md) | [中文](2026-10-02-backup-validation-coverage.zh.md)

## Contract

**[INV-SCHED-16] Backup Validation Coverage**: Validation excludes only backup activation combinations disproved by supported trigger logic, reports success only after every remaining combination passes the same merged-plan validation as shift projection, and preserves the caller's active plan and actual occupancy. Budget exhaustion is an incomplete warning that permits startup; confirmed configuration errors remain blocking.

The [subsystem contract](../../../../docs/subsystems/base-scheduler.md), [coding standards](../../../../CODING_STANDARDS.md) and [review checklist](../../../skills/mower-code-review/references/invariants-checklist.md) register this rule. The [simplification record](../simplification/2026-10-02-single-backup-validation.md) records caller evidence and removal of duplicate validation.

## Failure and implementation

The decoded Scheduling Plan contains six backups. `深海强制上班` assigns 八幡海铃 as 歌蕾蒂娅's replacement; `渡桥下班` assigns 八幡海铃 as a primary in another Control Center slot. Both triggers can hold when 歌蕾蒂娅 has mood above 23.5 and 渡桥 and 玛恩纳 are not working. The primary-name component graph omits their overlap. Shift projection rejects that overlap.

The validator uses the runtime merged-plan checker in independent operator models. Configuration failures identify the active backups and the same validation reason. Operator ownership precedes baseline validation. Candidate models omit actual-occupancy caches because configuration checks do not need observed mood or bed times.

AST analysis shares known operator working/resting calls, current-room and same-room facility-product string equality/inequality, plus clue-party null comparisons, including nested Boolean operators. Unknown, missing, unsupported, time-dependent or state-mutating triggers retain independent whole-trigger choices. Analysis does not execute expressions or read actual occupancy. This conservative fallback includes simultaneous expression failures and never treats a mood threshold or rescue call as a fixed shared value.

The admission budgets are 16384 distinct activation combinations and 262144 symbolic condition states. Exceeded budgets return `status: incomplete` with `success: false`. Startup logs a warning and continues; manual validation shows a warning. Confirmed configuration errors still block startup. The [warning decision](../feature/2026-10-02-backup-validation-warning.md) defines this distinction. Fourteen independent backups fit; twenty room-exclusive backups require twenty-one checks. There is no fixed table-count limit. Static validation covers merged configuration errors and does not prove all future dynamic convergence.

The [R.I.I.C-Calculator scheduler](https://github.com/Panda-Panta/R.I.I.C-Calculator/tree/main/src/scheduler) evaluates parsed conditions against simulation state and validates active merged plans. Its source is a reference for separating expression parsing from state evaluation; no source is copied into this implementation.

## Verification

Hermetic tests invoke real shift projection and manual validation on the decoded plan and assert the same failure. Replacing the conflicting replacement with 清道夫 passes all 32 candidate combinations. Tests cover three-way bed shortages, later overrides, invalid baselines, both budgets, missing operators, unknown expressions, resource-rejected strings and preservation of active conditions, operator identity and mood caches. Supported static conditions are checked against the real expression evaluator.

Twenty-backup shift-off and shift-on tests converge, and an activation oscillation raises an error while preserving the task and actual occupancy. The small-roster offline benchmark uses twenty repetitions: median shift projection is about 1.65 ms for one backup, 4.81 ms for six and 11.33 ms for twenty; the twenty-backup cycle is detected in about 13.06 ms. These host timings exclude device interaction and do not bound complex condition chains. Shift projection and complete shift convergence each have a 64-round limit; ordinary cached backup switching detects repeated activation vectors without a separate round limit.

## Standards Findings

PASS. Actual occupancy, active conditions and operator identity are preserved; ownership retains precedence. Analysis states and deduplicated combinations have finite budgets. Both glossary files and configuration schemas remain unchanged. Governance and formatting gates pass.

## Spec Findings

PASS. Manual and startup callers share the runtime merged-plan checker. The decoded Scheduling Plan fails with both conflicting backup names and the shift-projection reason. Corrected configuration coverage prunes impossible combinations; twenty mutually exclusive backups pass. Focused regression and adjacent scheduling suites pass, including warning startup and product-condition coverage. Dynamic convergence remains a runtime check.
