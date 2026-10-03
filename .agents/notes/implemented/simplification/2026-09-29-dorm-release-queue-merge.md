---
title: Dormitory release queue merge
status: implemented
category: simplification
date: 2026-09-29
---

# Dormitory release queue merge

## Contract

Ordinary Idle Dormitory Release tasks within the configured merge window share the latest scheduled time. Each dormitory has one queued task, with rooms ordered by dormitory number. Other task types, mandatory limits, workshop releases, and conflicting bed identities separate batches. Repeated scheduling retains the original window start and cannot repeatedly postpone the same release.

[INV-SCHED-03] retains each occupant's original room and slot. Execution verifies each member independently. Departures cancel only that member; changed recovery deadlines defer unfinished members. Failed selection restores unresolved Free slots for identity checks on retry.

## Simplification evidence

`collect_release_dorm_batch` has one caller and combines tasks only during execution. Queue-level merging in `merge_release_dorm` replaces that collector and its temporary multi-task mutation. `plan_metadata` merges after all task types are present; dispatch also normalizes newly inserted releases. The existing glossary definitions remain accurate.

## Verification

Offline tests reproduce six releases across three dormitories, per-person exclusions and cancellation, persistence, retry, unchanged merge windows, and barriers for order runs, training swaps, shifts, charging, workshop work, and mandatory limits.
