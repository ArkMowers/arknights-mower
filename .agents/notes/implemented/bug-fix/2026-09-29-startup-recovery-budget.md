---
title: Startup Recovery Budget Ownership
status: implemented
category: bug-fix
date: 2026-09-29
---

# Startup Recovery Budget Ownership

[中文](2026-09-29-startup-recovery-budget.zh.md)

## Contract

[INV-DEV-03] Startup Budget Isolation: Each new device startup establishes its Recovery Budget before preparation; preparation, readiness, validation and helper initialization share that deadline without inheriting a previous run's deadline.

`DeviceSession.begin_budget()` establishes the deadline. `DeviceControl._start()` binds the selected Device Profile and begins the budget before acquiring preparation resources. `ensure_ready(deadline=...)` preserves that deadline. Existing cancellation, Instance Binding and cleanup rules remain authoritative.

The existing Recovery Budget glossary definition remains applicable; this change adds no domain term or persisted configuration field.

## Verification

`arknights_mower/tests/device_session_tests.py` covers repeated runs beyond the old deadline, preparation time deducted from readiness, and preparation exhaustion before device probes with resource release. Existing readiness and preparation lifecycle tests cover recovery and compensation.

The focused suites run with `python -B -m unittest` because the local environment lacks pytest: 30 session tests and 45 preparation/lifecycle/governance tests pass. Application, caller and instance-start checks pass 28 tests; one existing application test supplies `{}` where `build_global_plan(include_source=True)` returns a pair. The same test fails with the pre-change startup method restored in memory.

Standards review passes for budget bounds, cleanup and target identity. Specification review passes for repeated starts and shared preparation/readiness deadlines. Governance checks pass; live device execution is outside this offline verification.
