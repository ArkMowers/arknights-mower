---
title: Shared Intelligent Rescue Planning
status: archived
category: simplification
date: 2026-10-03
---

> Superseded by [Configured Rescue Schedule](../../implemented/simplification/2026-10-04-configured-rescue-schedule.md).

# Shared Intelligent Rescue Planning

## Contract

[INV-SCHED-09] and [INV-SCHED-14] retain complete replacement matching, measured worker eligibility and isolated recovery planning. Initial staffing and rescoring share facility candidate preparation and ranking; callers retain their reservation sets, original-primary positions, operation budgets and persistence responsibilities. Initial staffing retains its current-roster tie preference; rescoring selects by facility score and mood.

One recovery-target update evaluates each complete group once, including unavailable native opportunities. Each member retains its own historical rate, cycle and target. The result is local to that call; the next update evaluates the current snapshot again.

## Simplification

The two staffing paths share their duplicated candidate preparation and fallback ordering. Group opportunity reuse avoids repeated identical snapshot searches without persistent caches or invalidation state. The unused staffing `initial` argument and redundant reservation alias are removed. The subsystem lifecycle definition is authoritative; the coding standard and review checklist retain their invariant registrations and link to that definition.

## Verification

Existing staffing and rescoring tests cover fixed-worker synergy, complete matching, reservations, mood eligibility and interrupted arrangements. Group-target tests cover available and unavailable opportunities, different member rates, missing history and fresh evaluation on the next update.

## Review

Standards Findings: PASS in the current chat. Shared candidate preparation has two production callers; reservations and persistence remain with those callers, and opportunity reuse is bounded to one update. The lifecycle definition retains all guarantees and the other invariant registrations link to it. Ruff and governance pass.

Spec Findings: PASS. The focused suite passes 319 tests and 4 subtests, covering staffing, rescoring, group reservations, returns, compensation and observation budgets. New group-opportunity controls fail before deduplication and pass afterward, preserving member-specific rates and cycles and recomputing on the next update.
