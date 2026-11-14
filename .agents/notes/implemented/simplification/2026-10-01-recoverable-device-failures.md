---
title: Recoverable Device Failures
status: implemented
category: simplification
date: 2026-10-01
---

# Recoverable Device Failures

## Contract

[INV-DEV-18] Recovery Cycle Continuation keeps transient device failures inside a finite Recovery Budget, retains the selected Instance Binding and repeats failed cycles only after cancellable cooldown; a verified ready observation supersedes an unconfirmed reconnect response.

[INV-SCHED-39] Pending Task Preservation retains the scheduler and pending tasks across device recovery, refreshes the Capture Frame before dispatch resumes and never repeats uncertain input coordinates. Unverified side effects pause device dispatch without ending the automation worker.

[INV-DEV-17] Pre-Input Helper Recovery repairs unavailable control helpers within the existing Recovery Budget after same-target validation. A healthy capture and ADB connection remain owned during input-only repair; MuMu IPC retains paired recovery. Ordinary graph navigation resumes from a newly observed scene, not from a saved command.

## Simplification

The application boundary replaces permanent transient-error latches with a recoverable failed state. Device Session remains the sole owner of lifecycle commands and per-cycle attempts; task supervision owns cancellable cooldown, not a second rapid restart loop. Startup and runtime recovery use the same supervisor. Successful final resource release supersedes an earlier interrupt error; actual cleanup failure still blocks replacement.

Screenshot recovery uses one helper rebuild per incident and same-target standard ADB validation for eligible DroidCast degradation. Persistent Device Profile selections and original helper diagnostics remain unchanged. Ownership conflicts, failed cleanup, IPC cohesion and configuration-size verdicts retain their boundaries.

Input preparation and transmission have distinct failure classifications. Unknown probe results never authorize input; finite re-probing or helper repair precedes any send. Unknown delivery propagates without replay. Only explicitly read-only navigation permits scene reconciliation; unverified side effects retain a local dispatch pause.

[INV-REC-03] Scene Recovery Limit keeps ordinary navigation recovery in its existing call stack and retains one game restart for recognition failures. MaaTouch handshake and scrcpy packet construction failures report known-unsent input; any preceding transmitted packet preserves delivery uncertainty. ADB connection failures use connection exceptions rather than internal-fault exceptions. Native Android recovery stays with its installed adapter and preserves its initial identity.

## Scope

All supported presets share these contracts. No remote configuration, running instance, shared ADB server or Scheduling Plan is modified. The startup protection setting remains in its existing advanced form and continues binding to simulator.wait_time. No glossary term or definition changes.

## Verification

Focused hermetic tests cover false reconnect responses followed by readiness, bounded helper repair, transient capture incidents, interrupt compensation, repeated finite recovery cycles, task preservation, refreshed navigation and cancellation. Tests never connect to live devices.

MaaTouch regressions cover termination before pipe closure, Windows and POSIX stop return codes, bounded terminate-to-kill escalation, and a real host-process exit between the last live check and termination through `Device.tap`. That exit pauses dispatch and the next input is not sent.
