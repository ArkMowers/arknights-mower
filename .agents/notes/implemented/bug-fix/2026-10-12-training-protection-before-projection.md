---
title: Training protection before shift projection
status: implemented
category: bug-fix
date: 2026-10-12
---

# Training protection before shift projection

## Decision

Ordinary shift projection applies the existing training correction policy before projecting original intent, backup actions or a complete-cycle step. This repair extends the evidence for [INV-SCHED-05]; it introduces no new invariant or domain concept. The [scheduling contract](../../../../docs/subsystems/base-scheduler.md#25-dynamic-shift-transition) owns the operational guarantee.

The training filter is shared with correction. Notification and stale-state cleanup remain in the correction entry point; projection invokes only the arrangement filter. Generic occupancy projection remains independent of mastery policy. This removes the need for a second assistant exclusion rule in dormitory candidate selection.

## Evidence

The supplied alpha.11 log observes 艾丽妮 and 克莱门莎 in training at 17:39:38. At 18:13:27 a backup projection proposes `train: ['望', '余']`. At 18:13:29 final dormitory filling names 艾丽妮, while the final arrangement omits the unconfigured training room. At 18:16:13 actual occupancy records 艾丽妮 in dormitory 2. Execution-only training protection cannot correct a dormitory target already derived from false projected availability.

The [complete-shift decision](../simplification/2026-09-29-complete-shift-convergence.md) owns convergence; the [shared-shift decision](2026-10-08-shared-shift-source-release.md) owns group confirmation after training slots are skipped. This decision owns applying that existing training policy before hypothetical displacement and dormitory admission.

## Verification

`shift_training_projection_tests.py` exercises actual backup and complete-cycle entry points with configured and unconfigured training rooms, protected assistants, database and queued mastery, observed training, assistant following and disabled automatic mastery. Against the original code, 12 of its 15 checks fail, including named dormitory admission of 艾丽妮 and incorrect backup condition evaluation. The repaired code passes these regressions.

The focused run of this suite, complete-cycle convergence, backup convergence, group training protection, base scheduling and backup relocation passes 234 tests. Ruff checks and formatting pass. Structural governance checks pass with two pre-existing archived-note reference warnings. Standards and requirement review confirm shared policy, projection isolation, unchanged correction notifications and preserved assistant-following behavior. Verification uses no live device. Glossary meanings remain unchanged.
