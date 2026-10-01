---
title: Different ADB Client Regressions
status: implemented
category: testing
date: 2026-10-01
---

# Different ADB Client Regressions

## Contract

[INV-01], [INV-03], [INV-05] and [INV-DEV-19] permit distinct ADB executable paths and release labels on the guarded shared server when their protocol versions agree. Protocol mismatch preserves the existing service and each instance's explicit selections. The [shared recovery decision](../../implemented/simplification/2026-10-01-shared-adb-recovery.md) defines the unchanged production contract.

## Test Boundary

The existing shared-server fixture maps each executable path to its protocol and release label. Two independent `SharedADBRecovery` coordinators use distinct paths with spaces and the same temporary coordination record. Tests alternate their calls deterministically; a separate spawned process exercises actual OS lock contention. Simulated probes, CLI responses and monotonic clocks replace device and service I/O.

The application fixture connects two `DeviceControl` sessions through `ProductionSessionADB`, with distinct executables, instance identifiers and pinned serials. A shared registration table loses its entries on server startup. CLI and frame responses reject target/path cross-routing, including when frame dimensions are varied. Adapter spies verify reconstruction requests; helper internals retain their dedicated suites. Injected preflight and simulator observations isolate the recovery boundary; these tests do not claim vendor discovery validation or live emulator coverage.

## Coverage

- Compatible executables with different release labels share a healthy server without restart actions or path replacement.
- Either executable starts an absent server; its compatible peer observes the same generation without another startup. An incompatible peer preserves the first starter's server, including an older protocol.
- Sustained host handshake failure permits one coordinated restart by either executable. The peer sees its generation, restores only its own target and reconstructs its helpers once. Failed-stop cooldown is shared across executable paths.
- One or both targets going offline on a healthy host permits targeted recovery, not shared-server restart. An incompatible instance preserves its healthy peer's dispatch and both configurations; restoring protocol compatibility permits recovery without replacing the service.
- A peer's invalid Capture Frame prevents helper reconstruction and generation binding until verification succeeds, without restarting the healthy peer or changing selections.
- Closing either instance releases its helpers without stopping the shared service or blocking its healthy peer's dispatch. Default coordination paths remain identical after recovery with different executables.
- The existing bounded cross-process lock test covers its original executable and both distinct executable paths; healthy observations remain nonblocking and absent-host lock contention consumes only the caller's deadline.

## Simplification and Verification

Path-specific response data extends the existing fixture instead of introducing another recovery implementation, simulator framework or production abstraction. Existing invariant registrations and glossary definitions remain unchanged. Focused shared-server, guard, application recovery and governance tests verify the fixture extension and preserve existing cases.
