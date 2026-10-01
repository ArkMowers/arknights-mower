---
title: Single Backup Validation Path
status: implemented
category: simplification
date: 2026-10-02
---

# Single Backup Validation Path

[English](2026-10-02-single-backup-validation.md) | [中文](2026-10-02-single-backup-validation.zh.md)

## Contract

The [backup validation contract](../../../../docs/subsystems/base-scheduler.md) owns **[INV-SCHED-16] Backup Validation Coverage**. Manual validation and startup use `Operators.validate_backup_plans`; combined configurations use the same `swap_plan(..., refresh=True)` check as shift projection.

## Simplification audit

Repository searches identify two callers of `Operators.validate_backup_plans`: the validation HTTP route and startup. `validate_backup_plans_offline` has no callers and duplicates the primary-name graph with weaker duplicate-only checks. `Plan.primary_names` serves only those validation graphs; no documented public contract refers to either unused interface.

The validator generates possible activation combinations from supported trigger logic instead of inferring independence from primary names. The unused duplicate validator and its primary-name helper are removed. At most 16384 distinct combinations and 262144 symbolic states are admitted; larger spaces return incomplete warnings that permit startup without claiming validation success. A specific budget exception separates these warnings from other errors. Candidate models clear actual-occupancy caches before configuration checks. Separate operator models preserve actual occupancy and the active Scheduling Plan. No scheduling execution or configuration schema changes.

## Verification

[Offline regression tests](../../../../arknights_mower/tests/backup_validation_tests.py) cover cross-backup replacements, three-way group capacity, override order, state isolation, admission limits the decoded six-backup Scheduling Plan and twenty-backup shift projection. [Condition analysis tests](../../../../arknights_mower/tests/backup_condition_coverage_tests.py) cover conservative exclusion and symbolic-state admission.
