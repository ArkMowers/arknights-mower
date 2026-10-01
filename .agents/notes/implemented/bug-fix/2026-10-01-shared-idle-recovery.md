---
title: Shared Idle Recovery
status: implemented
category: bug-fix
date: 2026-10-01
---

# Shared Idle Recovery

## Contract

[INV-DEV-14] Startup Reconnect Budget preserves the same bounded reconnect and observation policy after an instance launch or restart during an existing task as during initial startup. Each observation verifies the same Instance Binding; shared ADB failures, binding changes and cancellation remain terminal.

[INV-SCHED-12] Idle Lifecycle Ownership routes automatic idle shutdown through Device Control and the selected Device Profile. A confirmed stop permits one verified wake; failed or unsupported control never records a successful stop or substitutes legacy paths, another instance or a host-wide command. Android and physical devices remain outside desktop simulator lifecycle control.

[INV-DEV-17] Pre-Input Helper Recovery rebuilds a control helper proven unavailable before input only after revalidating the same Instance Binding within the Recovery Budget. Uncertain input delivery remains terminal without replay or an implicit touch backend switch.

## Boundary and simplification

Device Session owns launch, targeted reconnect and readiness polling for every supported simulator. A rejected reconnect during boot does not establish a successful connection or terminate the remaining observation budget. It consumes the existing action budget without another launch. Backend input failures never authorize replay of a potentially delivered command or an implicit switch to another touch backend.

The simulator compatibility entry delegates idle shutdown to the existing verified lifecycle adapters. Device Profile is authoritative for manager paths and instance identities; legacy simulator fields do not select a second control path. Existing owned-AVD shutdown restrictions remain effective.

Windows MuMu and LDPlayer stop adapters revalidate selected manager identity before issuing an index-based shutdown. Identity observation and shutdown share one deadline. Changed or ambiguous identity prevents the command; ADB readiness is not a prerequisite for a manager-verified stop. Device Control propagates binding failures as classified verdicts without entering scheduling recognition recovery.

The scrcpy control probe checks EOF without sending input or consuming buffered data. A healthy helper does not trigger a rebuild. A proven unavailable helper uses the selected backend and bounded recovery before the first input; liveness is checked again after rebuild. A transmission failure still terminates the task because Android receipt is unknown.

Scheduling dispatch, arrangement, MAA and local operation boundaries propagate classified device failures without consuming the pending task or invoking recognition recovery. Actual missed trade orders retain existing detection and replanning.

## Verification

Hermetic tests cover delayed ADB availability after runtime launch, persistent rejection, unchanged instance identity, action and deadline limits, shared ADB failure, cancellation, manager-path selection, failed shutdown and verified wake. Windows and macOS use the same recovery and shutdown contracts; tests replace all external processes and sockets.

Additional tests cover control EOF, preserved buffered data, pre-input rebuild, refused or exhausted recovery, healthy-helper reuse, uncertain delivery without replay and scheduling error propagation. The startup and runtime launch matrix covers each supported lifecycle preset without granting unsupported adapters new capabilities.

Remote diagnosis reads logs, device status and the selected manager instance without changing configuration or starting tasks.
