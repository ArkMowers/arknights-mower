---
title: MuMu Pro Idle Reconnect
status: implemented
category: bug-fix
date: 2026-09-30
---

# MuMu Pro Idle Reconnect

## Contract

[INV-DEV-14] Startup Reconnect Budget requires a rejected ADB reconnect during startup readiness to retain bounded retries and observation until the existing deadline. Each retry verifies the same Instance Binding. Binding changes, shared ADB errors and cancellation remain terminal; no other endpoint or repeated simulator restart is permitted.

## Boundary and simplification

MuMu Pro's running state and listening TCP port do not establish Android ADB readiness. `DeviceSession._wait_ready` uses the existing `_action` counter and `_wait_local` polling window rather than a separate MuMu Pro recovery loop. A rejected reconnect does not mark the serial as successfully connected. The remaining action budget permits another targeted reconnect; exhausted actions leave only read-only readiness polling within the same deadline.

## Verification

Hermetic tests reproduce a failed first reconnect after idle launch, eventual readiness, persistent failure, binding changes, shared ADB failure and cancellation. Successful recovery retains the selected instance and does not alter the saved endpoint. Remote diagnosis uses read-only logs and state queries; it performs no service restart or simulator lifecycle action.
