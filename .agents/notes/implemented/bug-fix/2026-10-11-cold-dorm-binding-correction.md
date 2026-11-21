---
title: Cold Dormitory Binding Correction
status: implemented
category: bug-fix
date: 2026-10-11
---

# Cold Dormitory Binding Correction

## Contract

[INV-SCHED-25] and [INV-SCHED-22] retain their existing meanings. The [scheduling contract](../../../../docs/subsystems/base-scheduler.md#211-multiple-group-bindings) owns cache-free dormitory correction and same-group replacement eligibility. The [explicit shift state decision](../../implemented/simplification/2026-10-07-explicit-group-shifts.md) owns group confirmation and persistence; this repair covers correction before a missing dormitory arrangement becomes a task.

## Cause and implementation

After cache clearing, the active binding starts at its configured first column. `correct_group_dorms` uses that column's group state even when an additional group is resting. If the dormitory primary occupies its configured slot, correction emits no target, so shared arrangement normalization has no position or transition to inspect. The same active-column assumption rejects an additional group's working primary as a same-group dormitory replacement.

Correction derives resting bindings from the existing group-state query and explicit correction transitions. Same-group primary eligibility uses those bindings. Replacement intersection, unique matching, unavailable-candidate checks and confirmation retain their existing owners. No new state map, configuration field or independent shift path is added. Domain names, meanings and relationships remain stable; the glossary remains unchanged.

## Verification

The focused cold-start suite passes 20 offline cases. Cases cover the first real planning entry, an unchanged primary position, wrong or missing covers, same-group primary replacements, Free opening, common and incompatible bindings, busy or reserved candidates, both final-return orders and failed confirmation. The unmodified alpha correction fails 5 of these 20 cases; the repair passes all 20. The final 20-suite focused scheduling, recovery, card and selection run passes 822 cases with one existing Pydantic serialization warning. Ruff and the three governance gates pass; governance retains two historical archived-reference warnings. No live device integration is run.

## Standards Findings

The simplification audit retains existing group-state and replacement helpers. Existing invariants cover the defect; no new invariant identifier is registered. Standards review finds no actionable defects: correction reuses the existing queries, leaves live state unchanged during planning, and preserves replacement matching, reservations and confirmation boundaries.

## Spec Findings

The alpha baseline reproduces the missing secondary-binding correction. The intermediate repair reproduces the separate same-group eligibility failure. Requirement review confirms cache-free secondary-binding restoration, common-cover constraints, both return orders and failed-confirmation preservation. The supplied report contains no runtime log or concrete roster; these cases establish defects in the current code without identifying the user's exact observed arrangement.
