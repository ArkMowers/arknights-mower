---
title: Discovery Worker Cancellation Context
status: implemented
category: bug-fix
date: 2026-09-30
---

# Discovery Worker Cancellation Context

## Contract

[INV-DEV-15] Settings Cancellation Isolation extends across parallel provider discovery. Each submitted provider receives its own copy of the caller's context. Settings capture-helper waits ignore a stopped task's signal and retain process shutdown and device closure cancellation without changing shared events.

## Boundary and simplification

The shared `_concurrent` submission boundary copies the context separately for every operation and invokes that operation through the copy's `run`. macOS and Linux provider sweeps share this boundary; no vendor-specific cancellation branch or additional wrapper is introduced. Provider context changes remain local, result ordering stays stable, and `MowerExit` reaches the existing HTTP cancellation boundary.

The [settings cancellation decision](../../implemented/bug-fix/2026-09-30-device-settings-cancellation.md) defines the request scope and HTTP verdict.

## Verification

Hermetic tests use the real `DiscoveryService`, `BlueStacksAirDiscovery`, and thread pool with simulated device I/O. They cover a stopped task followed by successful Air capture, shutdown or device closure during capture, `device_operation_cancelled` over HTTP, unchanged configuration and stop signals, caller-policy restoration, and simultaneous providers with independent context copies.
