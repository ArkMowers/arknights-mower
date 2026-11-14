---
format: decision
title: Room Operation Budget Classification
status: implemented
category: bug-fix
date: 2026-10-12
---

# Room Operation Budget Classification

## Problem

Ordinary room history previously included specialized run-order waiting. A trade-room report on 2026-10-12 at 15:06:03 contained `total_s=164.203` and `confirm.total_s=150.568`; admitting it into ordinary history produced a 212.044-second budget. Uniform 90-second dormitory allowances also combined ordinary arrangements and complete recovery ordering despite their different work.

Read-only observations from four instances that day contain 976 reports from 00:06 through 21:44. Filtering removes 238 specialized or unknown-task reports, 18 calls without selection, 12 training-room calls and five failed or deferred calls, leaving 703 successful ordinary operations. Whole `agent_arrange_room` wall-clock durations include navigation, selection, confirmation, room reads and successful internal retries. Recovery events are matched to room-call intervals. All dormitory operations fit 60 seconds in 96.8% of samples; work facilities fit 30 seconds in 74.09% and 45 seconds in 96.66%. The 155 complete two-selection recovery operations have P95 60.624 seconds. One recovery at 17:32:45 performed two selections and two confirmations inside one 45.842-second room call.

## Decision

The [phase-matched budget contract](../../../../docs/subsystems/base-scheduler.md#phase-matched-room-budgets) separates ordinary dormitory and complete recovery histories, with 60- and 75-second floors; changed work facilities retain 45 seconds. The [existing timing context](../../../../arknights_mower/utils/operation_timing.py) measures the whole call once and excludes specialized and unfinished operations. [Admission and runtime rechecks](../../../../arknights_mower/utils/scheduler_task.py) reuse the execution eligibility rule through a read-only target lookup, resolving Current slots from observed occupants without rewriting the task. Started restoration uses only the remaining ordinary arrangement budget.

This choice reuses the existing bounded history and recovery ownership. It introduces no setting, collector or independent task. Strict mood-limit protection and rescue room observations keep their 90-second floor; critical margins retain their existing contract. Existing domain concepts retain their meaning, so the glossary is unchanged.

## Alternatives considered

A 30-second work-facility floor covers only 74.09% of observed operations, so the existing 45-second floor remains. A uniform 60-second dormitory floor overlooks the extra selection and confirmation in complete recovery; its observed P95 is already 60.624 seconds, so that phase uses 75 seconds. Retaining uniform 90-second dormitory budgets reserves unnecessary time for ordinary arrangements and does not fix specialized waiting entering their history.

## Consequences

Ordinary operations can use more windows before critical tasks without inheriting specialized waits. Slow operations still raise their own phase budget through the recent maximum times 1.2 plus 15 seconds. Measurements from four instances on one day do not guarantee a device deadline; new device observations may justify revisiting the floors. Each phase retains only eight in-memory samples, which reset at process restart. No configuration or database migration is required. Raw instance logs remain outside the repository.

## Verification

Focused offline tests cover timing admission, complete recovery versus restoration, specialized operation exclusion, unfinished returns, independent histories, read-only prediction and existing priority protection. Representative coverage resides in [timing tests](../../../../arknights_mower/tests/operation_timing_tests.py), [recovery execution tests](../../../../arknights_mower/tests/dorm_recovery_tests.py) and [priority admission tests](../../../../arknights_mower/tests/priority_admission_tests.py). Against alpha `fa0ad401`, 17 focused suites pass all 753 tests. All three structural governance checks pass; two archived ADB test references retain existing compatibility warnings. Ruff and whitespace checks pass. Standards and requirement review finds no unresolved violations. Live device execution and deployment are outside this verification.
