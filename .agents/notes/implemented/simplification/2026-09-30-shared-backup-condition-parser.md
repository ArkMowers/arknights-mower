---
title: Shared Backup Condition Parser
status: implemented
category: simplification
date: 2026-09-30
---

# Shared Backup Condition Parser

[English](2026-09-30-shared-backup-condition-parser.md) | [中文](2026-09-30-shared-backup-condition-parser.zh.md)

## Contract

Backup capabilities depend on actual `op_data` method calls inside condition syntax. Literal strings do not grant capabilities. The [maintenance ordering record](../feature/2026-09-30-maintenance-backup-ordering.md) uses this rule alongside the existing rescue condition.

## Evidence and implementation

The pre-flight audit identifies the existing AST detector in `Plan.uses_rescue_condition` as the shared implementation for the two active condition capabilities. `Plan.uses_condition` owns parsing and call recognition; the rescue and maintenance properties each supply one method name. This avoids a second copy of the detector without adding a configuration registry or changing expression evaluation. Both properties have production callers in operator plan merging and validation.

## Verification

Existing rescue tests and maintenance tests cover nested calls, malformed conditions, and literal method-name strings. Domain definitions and persistent schemas remain unchanged.
