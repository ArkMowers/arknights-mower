---
title: Observed Group Return
status: implemented
category: bug-fix
date: 2026-10-10
---

# Observed Group Return

## Contract

[INV-SCHED-25] All ordinary fixed working members observed in their exact effective primary slots authorize a corrective group return. Dormitory residents, workaholics, shared primaries and eligible standby members do not provide confirmation anchors. Unknown positions, incomplete observations, unfinished arrangements and initialization retain the confirmed state. The corrective task restores dependent dormitory and shared positions; only successful target confirmation commits the return. Cached projections do not independently infer a return.

## Simplification

Correction uses the existing group transition and dormitory restoration paths. One observed working member supplies explicit return intent; complete shift projection removes unchanged staffing targets. Anchor eligibility reuses `Operators.is_group_shift_anchor`, including its standby exclusion after recovery promotion. No room-reader callback, separate recovery queue or persistent field is added.

When no ordinary non-specialized anchor exists, training members pass through `_suppress_train_correction` before supplying return intent. This replaces unconditional training exclusion with the existing scan, mastery and assistant-following boundary, without duplicating protection logic. The confirmed group state remains pending until dependent dormitory targets are observed.

## Cause and implementation

A confirmed resting state can outlive the actual return of all ordinary working members. Dormitory correction follows that state and retains a fixed replacement, preventing another group from using the same replacement. Ordinary observation creates corrective return intent after checking all working members and unfinished arrangement protection. Projection excludes explicitly returning groups from the same round of rest planning. Failed correction retains confirmed resting state and actual replacement protection.

## Verification

Focused offline tests cover the automation/perception shared replacement, partial and misplaced groups, unknown observations, unfinished selected, queued and suspended arrangements, due Fiammetta work, emergency protection, projection isolation, initialization and healthy operation. Another resting group retains its shared follower cover. Target confirmation precedes replacement release. Against alpha at `2c1f68a7`, ten focused scheduling and governance suites pass 545 tests, including standby exclusion before and after recovery promotion. Governance structure checks pass with two existing archived-reference compatibility warnings. Ruff checks and formatting pass. No live device participates in verification.

Training-only regressions exercise actual correction, full shift projection and target confirmation for assistant and trainee anchors. The cases include automatic mastery on/off, assistant following on/off, database and queued mastery work, observed training, protected room snapshots and disabled scanning. The unmanaged assistant cases fail before the repair because no correction is queued. Blocked cases retain dormitory replacements and confirmed resting state; permitted cases restore the dormitory primary before committing the return. After this repair, twelve focused scheduling and governance suites pass 702 tests, including 48 new training-only cases. Ruff and governance checks pass, retaining the same two historical compatibility warnings.

## Standards Findings

PASS for implementation, isolated projection, confirmation boundaries and automated governance. Existing group-transition and dormitory correction paths remain authoritative; no persistent field or configuration is added. Concept-impact review against alpha confirms that group state, occupancy and confirmation retain their existing meanings and relationships. This repair adds an operational reconciliation rule; the bilingual glossary remains unchanged.

## Spec Findings

PASS. Complete ordinary working occupancy schedules the missing dormitory return and permits shared-cover transfer in the same converged task. Partial occupancy and incomplete operations preserve confirmed state and replacement protection. The supplied log omits the cached group-state value and the preceding return operation; offline reproduction confirms this blocking mechanism without establishing the original initiating event.
