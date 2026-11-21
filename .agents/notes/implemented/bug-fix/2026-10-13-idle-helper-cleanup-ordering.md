---
format: decision
title: Idle Helper Cleanup Ordering
status: implemented
category: bug-fix
date: 2026-10-13
---

# Idle Helper Cleanup Ordering

## Problem

Idle shutdown previously stopped the simulator before DroidCast released its remote helper. The later selected-device cleanup failed with `adb: device offline`. Repeated close attempts retained the owner but recovery retried cleanup before reconnecting, preventing the transport repair needed by cleanup.

## Decision

Device Control releases capture and input resources before the selected lifecycle adapter stops the simulator. It restores a previously active session if that adapter reports no stop. Pending cleanup recovery restores the original Instance Binding through standard ADB readiness, retries retained owners and opens replacements only after successful cleanup within the same Recovery Budget. This extends the ordering at the [existing cleanup boundary](../../../../docs/subsystems/device-control.md#recoverable-owned-cleanup); the [retained-owner decision](../../implemented/bug-fix/2026-10-08-recoverable-device-cleanup.md) continues to own retry responsibilities. Unsupported idle-stop presets retain their active helpers.

## Alternatives considered

Ignoring offline during close permits a running but unreachable remote helper to lose its owner. Resetting the shared ADB server can disrupt other instances and does not establish ownership. Requiring cleanup before transport repair preserves ownership but leaves offline cleanup unable to recover.

## Verification

Four new reproduction tests failed before repair. The focused device, recovery, shutdown, ownership and scheduler suites pass 592 tests. [DroidCast regression tests](../../../../arknights_mower/tests/device_droidcast_tests.py) exercise real cleanup before simulator stop, failure preventing stop, selected transport recovery before replacement, failed-stop restoration, preserved foreign resources and uncertain-input pauses, cancellation and the shared deadline/action limit. [Idle lifecycle tests](../../../../arknights_mower/tests/device_idle_lifecycle_tests.py) cover unsupported presets and selected lifecycle adapters. Ruff and the three governance gates pass; governance retains two existing archived-reference warnings. macOS fixture paths use `TMPDIR=/private/tmp` to avoid the system temporary directory's symlink alias.

## Consequences

Cleanup can still fail when the selected instance remains unreachable. Such failure continues to block helper replacement. Recovery readiness can take the configured budget; it uses the existing session policy without an additional retry loop. These are execution-order changes; domain names, meanings and relationships are unchanged and require no glossary edit. Remote deployment and live idle/wakeup verification are outside local implementation evidence.
