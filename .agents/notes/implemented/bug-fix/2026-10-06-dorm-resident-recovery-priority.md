---
title: Resident Recovery Priority
status: implemented
category: bug-fix
date: 2026-10-06
---

# Resident Recovery Priority

## Contract

[INV-SCHED-20] includes unfinished existing residents in single-target competition when admission or a single-target resident change triggers cross-dormitory allocation. Ranking uses the shared dormitory priority and recovery deficit. Completed residents are not added as recovery candidates. Existing reservation, exclusion and personal-limit protections remain binding.

## Implementation

The shared admission planner detects the event before collecting candidates from projected beds. Direct arrangements, shift admission and idle filling use this same candidate set. Mood updates without admission or a single-target resident change do not trigger relocation. Planning preserves live positions, recovery markers and deadlines.

## Simplification

The correction uses the existing projection and ranking loop; no executor fallback, recurring task or independent ranking layer is added. Rescue recovery keeps its existing primary protection and capacity policy.

## Verification

Offline admission regressions cover all three callers, cross-dormitory allocation, multi-Free target departure, rear-bed departure, completed residents and stable replanning. Existing departure, isolation, recovery setup and reservation suites cover protected positions.

## Standards Findings

Pass: projection isolation, reservations and measured-state boundaries remain intact. The user approved both exact bilingual glossary additions. Ruff and all governance gates pass.

## Spec Findings

Pass: a high-priority replacement already in a rear bed competes ahead of an ordinary newcomer without removing either resident. Single-target resident changes trigger cross-dormitory allocation regardless of Free bed count. The focused suites pass 301 tests and 4 subtests.
