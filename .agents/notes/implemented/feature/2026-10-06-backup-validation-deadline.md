---
title: Startup Backup Validation Deadline
status: implemented
category: feature
date: 2026-10-06
---

# Startup Backup Validation Deadline

[English](2026-10-06-backup-validation-deadline.md) | [中文](2026-10-06-backup-validation-deadline.zh.md)

## Contract

[INV-SCHED-16] retains complete-coverage success, isolated Scheduling Plan checks and blocking confirmed errors. Startup condition analysis and merged-plan checks share a five-second monotonic budget after ownership and baseline validation. Exhaustion returns `incomplete` and permits startup. Manual validation has no elapsed-time budget; existing combination and symbolic-state limits remain active.

## Implementation

The same validator accepts an optional elapsed-time budget. Analysis checks the shared deadline before and after trigger parsing, during domain and symbolic-state enumeration, and after sorting. Merged-plan checks inspect the deadline before each combination and after successful checks. A confirmed error takes precedence over deadline exhaustion. Checkpoints finish the current synchronous operation; the five-second budget does not interrupt a single parse, sort or merged-plan check, and does not bound ownership synchronization or baseline validation. No validation continues in a background worker.

## Simplification audit

Startup and manual callers share `Operators.validate_backup_plans`; condition analysis has one production caller. A shared deadline check reuses the existing budget exception and incomplete result. No second validator, persistent setting or worker lifecycle is introduced.

## Verification

Virtual-clock regressions cover analysis and merged-plan exhaustion, confirmed-error precedence, caller isolation, successful checks within budget, untimed manual coverage and the startup budget argument. The [Scheduling Plan contract](../../../../docs/subsystems/base-scheduler.md) retains runtime validation and resource limits.

## Standards Findings

PASS. Existing domain terms and configuration schemas remain unchanged. The deadline uses monotonic time, no worker survives validation, and isolated models preserve caller state. Focused hermetic tests, Ruff and governance checks pass.

## Spec Findings

PASS. Deterministic tests verify the shared startup budget, untimed manual coverage, incomplete warnings and blocking confirmed errors. An offline fourteen-backup smoke check stops after 5.0012 seconds with incomplete coverage; checkpoint granularity and the ownership/baseline exclusions remain explicit.
