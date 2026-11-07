---
title: Complete Plan Binding Membership
status: implemented
category: bug-fix
date: 2026-10-07
---

# Complete Plan Binding Membership

## Contract

[INV-SCHED-31] Schedule membership includes the primary and replacements from every binding within each query's existing scope. Collection preserves declaration order, removes duplicate names and leaves configuration unchanged. Group shift candidates retain the binding-specific compatibility required by [INV-SCHED-25].

## Implementation and consumer audit

`all_replacements` supplies the same ordered union to raw document consumers and `Room.all_replacements`. Frontend `planReplacements` supplies the corresponding union to mastery context, operator replacement menus and rescue imports. These helpers replace repeated traversal without changing the stored first replacement column or additional binding columns.

- Ownership validation already calls `Plan.scheduled_names` for the main plan and all backups, including explicit backup tasks. It continues through the shared collector, with extra-only replacement ownership tests covering confirmed misses and owned operators.
- Backend mastery context includes every binding when excluding trainees and assistants and deriving central bonuses. Automatic training rejects a scheduled trainee before changing the room; manual training stops scheduling only after a valid active countdown is observed. Frontend warnings and idle filtering use the same coverage; training-room staffing remains scheduled but is excluded from the conflict set.
- Workshop recommendation exclusions include every binding while retaining the existing dormitory and workshop exceptions. Manually configured workshop operator choices retain their existing behavior.
- Resting priority recognizes extra-only replacements as replacements. Rescue standby classification uses the normal main plan's complete membership; explicit ready, staffing and release reservations retain priority.
- Trade order detection collects markers from every binding in the effective plan, including rescue trade order lists. Task construction selects a trade order operator from the collected list instead of selecting an ordinary replacement preceding it. Rescue imports collect trade order markers before clearing normal shift groups; Fiammetta targets retain their existing separate semantics.
- Runtime `Operator.replacement`, exhaustion coordination and correction checks retain the selected binding or common compatible candidates. They do not use the configuration-wide union as permission to work for another group. Fiammetta rejects multiple bindings and keeps its charging target list. Independent rescue worker replacement lists retain their separate single-group staffing contract.

## Verification

Offline coverage exercises raw and validated documents, main and backup tables, duplicate names, unchanged configuration, facility exceptions, assistant exclusion, automatic trainee deferral, confirmed manual-training stop, ownership verification, recovery priority, rescue reservations and actual trade order tasks. Existing shared-group tests verify distinct and common replacements remain separate in scheduling. Frontend tests cover warnings, idle membership, central bonuses, operator replacement collection and rescue import preservation. No live device or account synchronization participates in tests.
