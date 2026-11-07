---
title: MuMu Pro Manager Preparation Cancellation
status: implemented
category: bug-fix
date: 2026-09-30
---

# MuMu Pro Manager Preparation Cancellation

## Contract

[INV-DEV-15] Settings Cancellation Isolation covers MuMu Pro manager preparation. Shutdown or device closure cancels preparation at command, polling and completion boundaries. No subsequent manager command executes after cancellation is observed, and HTTP returns `device_operation_cancelled` rather than success. A stopped task's signal remains unchanged and does not cancel settings preparation.

## Boundary and simplification

`MuMuProController.prepare_manager` uses the existing scoped `csleep` for cancellation checks and its default polling wait. `DeviceControl.prepare_mumu_pro_manager` rechecks that policy before publishing success. Preparation retains its single monotonic deadline, one application-open attempt and existing command timeouts; an in-flight command remains bounded by its timeout. No additional cancellation callback, vendor policy or retry wrapper is introduced. Instance startup, shutdown and shared ADB behavior remain unchanged.

The [settings cancellation decision](../../implemented/bug-fix/2026-09-30-device-settings-cancellation.md) defines the request scope and HTTP boundary.

## Verification

Hermetic tests use real `DeviceControl`, `DeviceSession`, `ProductionSimulator` and `MuMuProController`, with simulated process I/O. Shutdown and closure cover `port`, application open, inventory query, polling and completion boundaries, direct calls and both settings HTTP routes, with task stop signals set and unset. Tests verify unchanged configuration and task signals, cancellation-policy restoration and successful stopped-task preparation. Air test fixtures register canonical application paths, matching production discovery when temporary directories have symlink aliases.
