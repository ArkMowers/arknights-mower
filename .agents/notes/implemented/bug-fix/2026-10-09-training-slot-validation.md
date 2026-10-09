---
title: Training Slot Validation
status: implemented
category: bug-fix
date: 2026-10-09
---

# Training Slot Validation

## Contract

[INV-SCHED-44] rejects named training-slot assignments with synchronized basic skill level below seven or all skills at mastery three before manual validation or startup succeeds; assistant slots and placeholders are exempt, and missing skill fields request synchronization.

## Implementation

The shared Scheduling Plan roster precheck inspects the second training-room slot, all its binding replacements, and explicit backup staffing tasks. Existing ownership and training checks share one cache read and at most one refresh. Missing roster data retains the existing compatibility behavior; a failed refresh does not suppress a known training eligibility error. Same-name forms pass when an owned form meets both requirements. Confirmed ownership misses direct users to acquire the operators and then manually click Refresh on Growth Planning. Insufficient basic skill levels direct users to reach seven and refresh there; fully mastered trainees require replacement, and unknown fields or invalid caches request the same manual refresh. Mastery admission messages use the same page and button names. Existing glossary terms remain accurate.

## Simplification Review

The existing `validate_owned_operators` entry has one production caller in `Operators.validate_backup_plans`, shared by manual validation and startup. Extending that precheck avoids a second roster reader, synchronization path or frontend rule. The change adds no configuration schema or scheduling state.

## Verification

Offline tests cover main and backup assignments, replacement lists, backup tasks, basic skill six versus seven, partially mastered versus fully mastered skills, unavailable skill data, assistant and placeholder exemptions, stale-cache refresh, eligibility changes discovered during ownership refresh, one shared refresh for simultaneous failures, and explicit condition and page guidance after successful or failed synchronization.
