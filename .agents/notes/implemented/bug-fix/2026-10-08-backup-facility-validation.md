---
title: Backup Facility Validation
status: implemented
category: bug-fix
date: 2026-10-08
---

# Backup Facility Validation

## Contract

[INV-SCHED-34] preserves the primary production facility types and slot counts across backup plans. Manufacturing and trading facility levels follow their configured slot counts. Explicit staffing tasks fit the primary slots, including Current placeholders. Product and order targets remain equal to the primary targets when automatic switching is disabled.

## Implementation

`validate_backup_facilities` checks declared backup layouts, tasks and product targets before combination analysis. Validation reports the backup name, room and conflicting targets, returns failed status and prevents startup even when the combination budget is exhausted. Production room declarations retain the complete primary slot count; nonproduction partial staffing overlays retain their existing semantics. Task prefixes within capacity remain valid.

`Operators.swap_plan` rechecks active backup constraints with the current product-switching setting before changing plans, configuration, operators or dormitories. Failed activation returns an error and preserves existing live state. Facility switching has no implemented mode and remains prohibited; no speculative setting is added.

Automatic product and order switching defaults to disabled in the backend model, runtime compatibility checks and frontend configuration defaults. Missing legacy enable fields remain disabled; explicit enabled values survive loading and serialization. Disabled frontend trigger editors hide product-related choices until the user enables switching. Tests of enabled switching set the option explicitly.

Simplification inspection keeps the static check in the existing backup-validation module and reuses it for startup, manual validation and runtime activation. No new schema, facility operation or UI workflow is introduced.

## Verification

Offline tests cover larger and smaller production layouts, changed facility types with named and Current operators, task overflow with every placeholder, disabled and enabled product switching, unchanged products, valid nonproduction partial overlays and runtime rejection without state mutation. Replaying the supplied decoded schedule produces an explicit room_1_3 task error for the third Current. This replay reads configuration only and does not operate a device.

## Standards Findings

PASS: Validation reuses existing primary facility metadata and structured verdicts. Runtime rejection precedes mutation; bounded declaration checks do not execute trigger expressions. The invariant is registered in the subsystem contract, coding standards and review checklist.

## Spec Findings

PASS: Unsupported facility changes and disabled product switching cannot silently alter backup targets. Invalid explicit tasks fail before combination analysis; the execution boundary retains its existing stop behavior.
