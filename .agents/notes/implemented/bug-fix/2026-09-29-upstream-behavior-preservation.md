---
title: Upstream Behavior Preservation
status: implemented
category: bug-fix
date: 2026-09-29
---

# Upstream Behavior Preservation

[中文](2026-09-29-upstream-behavior-preservation.zh.md)

## Contract

- [INV-DEV-04] Launch Protection: A session preserves the bound instance's configured startup interval before a subsequent automatic restart; waiting remains inside its Recovery Budget and respects cancellation.
- [INV-DIAG-01] Archive Deletion Cohesion: Error archive deletion holds the store's archive lock and cancels its queued writes and active windows before late frames can recreate it.
- [INV-DIAG-02] Archive Error Isolation: Invalid metadata in one error archive produces a diagnostic without terminating the archive worker.

`DeviceControl` passes the existing `simulator.wait_time` to `DeviceSession`. Launch timestamps remain transient, persist across recovery of the same Instance Binding, and clear when the binding changes. Readiness during the protected interval avoids a restart. Budget exhaustion never authorizes an early stop.

`ScreenshotStore` owns expiry and capacity deletion through its existing locked deletion path. The ordinary frame cleaner retains bounded batches. Metadata handling covers malformed objects and missing fields.

The existing Recovery Budget, Instance Binding and Capture Frame glossary definitions remain applicable. No persisted configuration field or domain term is added.

## Verification

Offline tests cover startup protection in scheduled and explicit launch paths, budget exhaustion, cancellation, rebinding, archive retirement, metadata isolation and retained mood/backup-plan initialization behavior. Transport recovery without a valid frame does not authorize a restart; an unconfirmed reconnect remains a failure after the protected wait.

Desktop and application tests use the current lifecycle and plan interface, with no live device or update execution. The desktop fixture owns its shutdown state and mocks the HTTP lifecycle. Configuration tests close SQLite handles, read UTF-8 explicitly, and distinguish read-only previews from explicit saves.

Verification passes: device control (183 tests), explicit platform launch routes (45), diagnostics and desktop lifecycle (205; one platform skip and one subprocess integration exclusion), scheduling and mood (252), and configuration plus bound launch (69, including nine tests also counted in device control). Ruff checks and the repository governance gates pass.

The [archive deletion decision](../simplification/2026-09-29-archive-deletion-owner.md) records the ownership simplification.
