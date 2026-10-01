---
title: Shared ADB Recovery
status: implemented
category: simplification
date: 2026-10-01
---

# Shared ADB Recovery

## Contract

[INV-DEV-19] Shared ADB Recovery replaces owned foreground takeover with one guarded shared-server route. [Device Control](../../../../docs/subsystems/device-control.md) defines host-failure classification, coordinated restart, same-target verification and helper reconstruction. [INV-05] continues to prohibit implicit `kill-server`; an explicit, bounded host-recovery action is distinct from CLI mismatch handling. Device offline status and version mismatch alone never authorize restart.

This decision supersedes [Owned ADB Recovery](../../archived/architecture/2026-10-01-owned-adb-recovery.md).

## Simplification Evidence

The superseded `OwnedADBServer` design has one production construction site in `application.py`. Its ownership context spreads through ADB server, socket and session boundaries, screenshot helpers, AVD, LDPlayer and Nox adapters, and MAA scheduling. Those callers propagate one service choice rather than require independently owned services.

Removing the foreground child, listener ownership checks, private-port allocation, SDK-release gating, takeover negotiation and private helper routing eliminates a second service lifecycle. The shared ADB boundary retains socket negotiation, compatible binary checks and one host-shared recovery coordinator with cross-process locking. No replacement wrapper, Device Profile field, global server environment override or independent recovery loop is introduced.

## Recovery and Continuation

At least two failed host protocol handshakes sustained for at least thirty monotonic seconds admit explicit host recovery. A host-shared cross-process lock, persisted wall-clock cooldown and locked re-probe coordinate the bounded restart; a healthy re-probe skips it. Destructive-restart cooldown defaults to thirty seconds and is bounded between zero and sixty seconds. Lock waiting, commands and post-start verification share the current monotonic Recovery Budget and action limit. Cancellation and caller budget exhaustion never advance host-failure evidence. Shared-server restart can interrupt other host clients and is never ordinary target cleanup.

Only `SharedADBHandshakeTimeout` supplies restart evidence; malformed responses and other unverified host errors preserve the listener. A confirmed absent service permits guarded startup without `kill-server` and is not subject to destructive-restart cooldown; it is not a restart of an existing service.

`DeviceControl` receives `SharedADBRecovery` from `adb_client/shared.py` through `adb_recovery`. `recover` accepts `timeout`, `cancelled` and `action`; the coordinator has no `close` method. Its `.generation` exposes restarts across processes, not only restarts initiated by this session.

A verified healthy compatible server reads generation metadata without acquiring the recovery lock or creating a marker. An unreadable or malformed record emits one warning and invalidates local helpers once, without blocking startup or permitting a destructive restart. A server that becomes healthy immediately before mutation returns a successful no-op through the session action boundary. Explicit stop validates the `host:kill` acknowledgement before waiting for server disappearance.

Application sessions preserve the original Instance Binding, revalidate it after restart and reconstruct all capture and input helpers before dispatch, including after peer-process restarts. Successful helper binding records the shared-server generation; failed frame verification cannot restore stale helpers. Shutdown releases application-owned resources without stopping the shared service. Pending scheduler tasks and uncertain-input pauses survive; uncertain input is not replayed.

[Base Scheduling](../../../../docs/subsystems/base-scheduler.md) retains the existing truthful worker status: initialization reports `starting`, device repair reports `recovering`, and only an absent or completed worker reports `stopped`. Stop stays available and settings retain their target ownership lock until worker completion. These status changes remain independent of ADB service selection.

## Verification Boundary

The [portable lock-byte test](../testing/2026-10-01-adb-lock-byte-test.md) verifies persisted generation during a failed stop without reading the locked marker byte on Windows.

The implementation and test owners use `adb_shared_server_tests.py` and `adb_shared_transport_tests.py`, matching the desktop CI paths and this sidecar. Focused hermetic coverage substitutes probes, processes, locks and clocks; it covers healthy-service offline targets, version mismatch, host failure count and thirty-second duration thresholds, concurrent processes, shared cooldown, healthy locked re-probes, cancellation, budget exhaustion, failed restart verification, shared routing and same-target helper reconstruction.

`device_adb_recovery_tests.py` covers the application coordinator, peer-process generation changes, same-target verification, helper reconstruction, cancellation and action budgets. `device_control_shutdown_tests.py` retains deferred and idempotent helper cleanup coverage. `scheduler_recovery_preservation_tests.py` retains task continuity coverage. `server_status_tests.py` and focused frontend status and device-settings tests retain startup/recovery labels, Stop availability, metadata and settings-lock coverage. CI retains those existing status regressions while replacing owned-server suite names.

Focused hermetic tests verify the shared coordinator, target reconstruction and worker status. A local shared-ADB smoke check verifies protocol compatibility and reads the device list without starting or stopping a service or dispatching device input; the connected device list is empty. The existing glossary's implicit `kill-server` prohibition remains unchanged.
