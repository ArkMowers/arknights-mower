---
title: Backup Relocation Rest State
status: implemented
category: simplification
date: 2026-10-06
---

# Backup Relocation Rest State

Same-primary relocation reuses the existing backup replacement matcher and transition boundary. Both independent backup checks and complete shift projections use this boundary; no additional planner is introduced.

[INV-SCHED-28] extends state preservation to primary relocation between slots of the same facility type with unchanged ordered group bindings. Working primaries move to their destination; resting primaries retain beds and deadlines while available covers move or replace them. Explicit entry staffing tasks retain precedence. Exit restoration uses covers for preserved primaries rather than forcing primary recalls. Task-only exits also check unchanged slots: recovering primaries retain covers, group dormitory positions follow the group state, and primaries without recovery retain default restoration. Reservations, mastery protection and unrelated occupied slots remain binding.

## Verification

Offline regression tests cover downshift-triggered relocation, exit while a second group remains resting, cover migration, explicit entry tasks and protected shortages.
