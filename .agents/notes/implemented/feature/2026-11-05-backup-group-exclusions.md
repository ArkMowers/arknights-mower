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

Select compatible eligible groups in configured priority order. Explicit exclusions are symmetric. Each selected group has one exclusive-backup slot; a shared backup occupies all selected memberships. Global overlays remain scoped by group membership and merge once in backup order. Preserve legacy group exclusions during import. Default-group backups remain fallback-only.

## Alternatives considered

Adding a domain or scenario layer makes independent selections possible but complicates editing and nesting. Arbitrary backup exclusions distribute configuration across many backups. Directed group suppression adds a second priority relation and cycle handling. Group exclusions reuse the existing group order and let users configure relationships once.

## Verification

The focused native suites pass 358 tests, including complete-shift activation and persisted tuple state, full cross-group validation failures, fallback, condition correlation, snapshot isolation, shared exclusive slots and unchanged-state convergence. Frontend and simulator suites pass 154 tests for symmetric editing and removal, legacy and parallel JSON persistence, priority selection, per-group choices and projected activation. Production build includes the income Worker. Offline browser interaction confirms symmetric exclusions and the new `True` condition. No live device was used.

## Consequences

Concurrent groups can create additional combined staffing conflicts. Older versions select only one group and do not honor parallel configuration; restoring the pre-upgrade configuration restores the previous selection rules. Shared exclusive backups can reduce the number of simultaneously selected alternatives because selection preserves current backups rather than maximizing count. The user approved the exact bilingual glossary definition. New groups default to `True`; legacy missing and explicit empty conditions remain inactive. Exclusion lists preserve old group incompatibilities, while conflicts now follow group list priority rather than retaining a lower-priority current group.
