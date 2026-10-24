---
title: Intelligent Rescue Startup Progress Lifecycle
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Startup Progress Lifecycle

## Contract

[INV-SCHED-03] resumes unfinished startup observations even when intelligent rescue is disabled. The setting blocks new rescue episodes; it does not discard pending observation responsibilities. An empty room list retains its completed-read meaning while card scanning waits. Successful initialization persists cleared progress and an open initial mood gate. Later startups load room progress only from an unfinished-initialization snapshot.

## Simplification

The existing startup dispatch condition includes the nullable pending room list. Snapshot loading uses the existing initial mood gate, and startup completion uses the existing state save. No migration, compatibility path or additional state field is introduced. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the interface guarantees.

## Verification

Offline tests invoke real simulate initialization with device and maintenance boundaries isolated. They cover enabled and disabled settings, empty and nonempty progress, completed snapshots and a disable/restart/complete/re-enable sequence. Re-enabled startup reads all rooms after the previous initialization completes; disabled completion creates no rescue episode.

Focused observation, initialization, intelligent rescue, compensation and scheduling suites pass: 623 tests and 26 subtests. Scoped Ruff checks and formatting pass.

## Review

Standards Findings: existing observation persistence has an explicit completion boundary.

Spec Findings: disabling and re-enabling does not retain a stale list that skips measured startup readings.
