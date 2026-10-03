---
title: Release Planning Log Level
status: archived
category: bug-fix
date: 2026-10-04
---

# Release Planning Log Level

Superseded by [Initial Fiammetta and Release Stability](../../implemented/bug-fix/2026-10-04-initial-fia-and-release-stability.md). Unchanged release tasks are reused; actual advance notices remain visible.

## Contract

[INV-SCHED-03] preserves personal-limit release deadlines and operation windows. Rebuilding a release task records its computed advance at DEBUG level; it does not announce a new execution to the user.

## Simplification

The shared release planner recreates tasks during recovery. The existing WebSocket INFO threshold hides internal planning details; no deduplication cache or scheduling state is required.

## Verification

The deadline and Ling/Xi suites pass 66 tests, including repeated planning and changed deadlines. The broader personal-limit suite has 98 passes and 8 rescue-exit failures reproduced with the pre-change production code. Governance checks validate documentation.

## Standards Findings

The existing logging boundary preserves scheduling state and resource ownership. No glossary or configuration change is required.

## Spec Findings

Repeated advance calculations remain available in debug logs without repeated ordinary interface messages.
