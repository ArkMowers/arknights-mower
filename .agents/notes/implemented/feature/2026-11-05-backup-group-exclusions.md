---
format: decision
title: Concurrent backup groups with explicit exclusions
status: implemented
category: feature
date: 2026-11-05
---

# Concurrent backup groups with explicit exclusions

## Problem

[Backup Group Selection](../../../../docs/subsystems/base-scheduler.md#backup-group-selection) previously selected one group and one exclusive backup across that group. Independent trade and manufacturing alternatives cannot run concurrently without becoming global overlays.

## Decision

Select compatible eligible groups in configured priority order. Explicit exclusions are symmetric. Each selected group has one exclusive-backup slot; a shared backup occupies all selected memberships. Global overlays remain scoped by group membership and merge once in backup order. Preserve legacy group exclusions during import. The initial implementation retained default-group fallback from single-group selection. This prevented default backups from ever participating when custom conditions covered every state, such as working and resting. The default group now participates alongside custom groups; its backups still require their own conditions.

## Alternatives considered

Adding a domain or scenario layer makes independent selections possible but complicates editing and nesting. Arbitrary backup exclusions distribute configuration across many backups. Directed group suppression adds a second priority relation and cycle handling. Group exclusions reuse the existing group order and let users configure relationships once.

## Verification

The initial focused native suites passed 358 tests, including complete-shift activation and persisted tuple state, full cross-group validation failures, fallback, condition correlation, snapshot isolation, shared exclusive slots and unchanged-state convergence. Initial frontend and simulator suites passed 154 tests for symmetric editing and removal, legacy and parallel JSON persistence, priority selection, per-group choices and projected activation. Production build includes the income Worker. Offline browser interaction confirms symmetric exclusions and the new `True` condition. No live device was used.

The default-group correction is covered by native selection and combined-roster validation tests, simulator selection tests and the supplied plan in [`incomeDefaultGroup.test.js`](../../../../ui/src/riic/incomeDefaultGroup.test.js). Both Aroma working states apply and remove Fartooth resting priority as her condition changes; the full 3-day warmup and 28-day sample activates and deactivates that backup without modifying the plan. This uses maximum operator practice and unlimited materials, not a captured roster or inventory.

## Consequences

Concurrent groups can create additional combined staffing conflicts. Older versions select only one group and do not honor parallel configuration; restoring the pre-upgrade configuration restores the previous selection rules. Shared exclusive backups can reduce the number of simultaneously selected alternatives because selection preserves current backups rather than maximizing count. The user approved the exact bilingual glossary definition. New groups default to `True`; legacy missing and explicit empty conditions remain inactive. Exclusion lists preserve old group incompatibilities, while conflicts now follow group list priority rather than retaining a lower-priority current group.
