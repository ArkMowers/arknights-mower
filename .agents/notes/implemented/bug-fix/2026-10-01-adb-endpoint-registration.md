---
title: Bound ADB Endpoint Registration
status: implemented
category: bug-fix
date: 2026-10-01
---

# Bound ADB Endpoint Registration

## Contract

[INV-03], [INV-DEV-14] and [INV-DEV-19] require recovery of the original Instance Binding after shared-server registration loss. Read-only discovery and settings checks never register transports. Runtime registration, identity verification and helper reconstruction share the existing Recovery Budget; registration acknowledgement alone never authorizes dispatch.

## Simplification Evidence

`DeviceSession` already calls `ProductionSessionADB.recover` during local recovery and launch readiness. Both paths permit an unresolved Nox endpoint to use that boundary with its saved VM identity, not its saved serial. `NoxBindingReader.recover` reuses the existing guarded TCP disconnect/connect implementation through a callback. No simulator recovery interface, Device Profile field, independent retry loop or shared-server restart rule is added.

Nox recovery verifies the current UUID, Topology Fingerprint, unique title and running state. It reconnects only enabled loopback guest-port-5555 forwards in that VM's current configuration. PID, title, state and forwardings are rechecked before each reconnect and after registration; manager and direct boot identities still agree before a serial is exposed. Pending registration returns a retryable result, while changed or ambiguous identity retains a classified failure. Persistent configuration remains unchanged.

For a selected `emulator-*` alias, an exact `connect emu:console,adb` registration response admits readiness observation. An exact already-registered response instead executes the existing targeted `-s serial reconnect`; both commands share one deadline. Responses for other ports or targets never count as success.

The session action boundary propagates its deadline and cancellation through `device_io_budget`; command windows inherit that scope before each command. Cancellation during manager inspection prevents registration, and cancellation after targeted disconnect prevents the next connect. These checks apply to all session recovery adapters without a Nox-specific cancellation policy.

## Verification

Hermetic tests cover shared-generation changes with lost Nox registration, offline recovery, cold launch, stale saved serials, wrong boot identity, instance changes, read-only preflight, cancellation between commands and finite retry budgets. Emulator-alias tests cover targeted reconnect, rejected responses, cancellation and deadline exhaustion. The [shared-server recovery decision](../../implemented/simplification/2026-10-01-shared-adb-recovery.md) and [portable Windows lock-byte test](../../implemented/testing/2026-10-01-adb-lock-byte-test.md) retain their existing contracts. Existing invariant registrations and glossary definitions remain sufficient and unchanged.
