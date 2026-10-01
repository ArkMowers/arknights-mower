---
title: Shared Backup Condition Parser
status: implemented
category: simplification
date: 2026-09-30
---

# Shared Backup Condition Parser

## Contract

Backup capabilities depend on actual `op_data` method calls inside condition syntax. Literal strings do not grant capabilities. `Plan.uses_condition` owns parsing and call recognition for the [maintenance ordering contract](../feature/2026-09-30-maintenance-backup-ordering.md). Retired rescue calls are handled by configuration AST migration, outside runtime expression evaluation.

## Verification

Maintenance and retired-condition migration tests cover nested calls, malformed expressions and literal method-name strings. [MAA assisted emergency recovery](../../implemented/simplification/2026-10-02-maa-assisted-emergency.md) specifies the removed rescue capability.
