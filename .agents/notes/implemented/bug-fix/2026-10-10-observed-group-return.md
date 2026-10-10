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

## Cause and implementation

A confirmed resting state can outlive the actual return of all ordinary working members. Dormitory correction follows that state and retains a fixed replacement, preventing another group from using the same replacement. Ordinary observation creates corrective return intent after checking all working members and unfinished arrangement protection. Projection excludes explicitly returning groups from the same round of rest planning. Failed correction retains confirmed resting state and actual replacement protection.

## Verification

Focused offline tests cover the automation/perception shared replacement, partial and misplaced groups, unknown observations, unfinished selected, queued and suspended arrangements, due Fiammetta work, emergency protection, projection isolation, initialization and healthy operation. Another resting group retains its shared follower cover. Target confirmation precedes replacement release. Against alpha at `2c1f68a7`, ten focused scheduling and governance suites pass 545 tests, including standby exclusion before and after recovery promotion. Governance structure checks pass with two existing archived-reference compatibility warnings. Ruff checks and formatting pass. No live device participates in verification.

## Standards Findings

PASS for implementation, isolated projection, confirmation boundaries and automated governance. Existing group-transition and dormitory correction paths remain authoritative; no persistent field or configuration is added. Concept-impact review against alpha confirms that group state, occupancy and confirmation retain their existing meanings and relationships. This repair adds an operational reconciliation rule; the bilingual glossary remains unchanged.

## Spec Findings

PASS. Complete ordinary working occupancy schedules the missing dormitory return and permits shared-cover transfer in the same converged task. Partial occupancy and incomplete operations preserve confirmed state and replacement protection. The supplied log omits the cached group-state value and the preceding return operation; offline reproduction confirms this blocking mechanism without establishing the original initiating event.
