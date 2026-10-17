---
title: MuMu Startup Command Deadlines
status: implemented
category: bug-fix
date: 2026-10-03
---

# MuMu Startup Command Deadlines

[English](2026-10-03-mumu-startup-command-deadline.md) | [中文](2026-10-03-mumu-startup-command-deadline.zh.md)

## Contract

[INV-DEV-20] Command Output Ownership bounds MuMu startup observations and default guarded ADB command waiting independently of inherited output handles. Timeout terminates only the owned command, attempts reaping for at most one additional second and preserves the Instance Binding and shared services. [Device Control](../../../../docs/subsystems/device-control.md) owns the interface contract. The [shared execution decision](../simplification/2026-10-03-device-command-output.md) defines runner reuse.

## Evidence Boundary

The reported UI stops after connection readiness while the selected MuMu instance remains on its desktop. UI logs expose INFO and higher; intermediate startup operations otherwise expose DEBUG. The report supplies no DEBUG file log after the connection message and no access to the affected host. It therefore does not establish the incident's root cause.

A Windows Python 3.12 offline fixture invokes the production preflight adapter with a 0.5-second timeout and a descendant retaining stdout/stderr. Both a sleeping command and a command that exits successfully remain blocked beyond two seconds in the pipe-based implementation. Releasing the descendant permits return. This confirms a reproducible command-lifetime defect independently of the incident.

## Implementation

Preflight, MuMu input version queries, ADB command execution, shared-server version checks and startup use `run_command`. Default vendor observations use the same bounded mechanism. Captured streams use temporary files and finite reads; output collection never waits for descendant EOF. Command arguments, hidden Windows creation flags, Shared ADB Guard, return-code errors, binary Capture Frame data and text decoding retain their existing roles. No new retry or host-wide cleanup is added.

Device Control emits INFO when preflight starts, when helper initialization starts, and after initialization completes. DEBUG command boundaries identify the external operation and its effective timeout. The [startup diagnostic recipe](../../../../docs/cookbook/device-startup-stall.md) distinguishes command blocking, budget-limited waiting and UI delivery failure.

## Verification

Focused offline tests cover inherited stdout/stderr, normal completion, timeout, separate and merged output, binary/text decoding, output limits, process reaping, stream closure and the selected-target startup failure verdict. Device and network operations remain isolated. Confirmation on the report host still requires its DEBUG file log or a run with this change.

Validation passes 509 focused tests and 193 subtests, including MuMu Pro, DroidCast, Shared ADB Guard, session startup and repository governance. Ruff checks, formatting and diff whitespace checks pass.

## Standards Findings

PASS: The shared runner implements [INV-DEV-20] without reader threads or descendant termination. Shared ADB negotiation and instance identity remain intact. Startup failure exposes the existing `frame_failed` verdict and releases the settings lock. Existing glossary definitions cover these execution bounds; persisted fields and domain meanings retain their contracts. Targeted tests, Ruff, documentation links and repository governance checks pass.

## Spec Findings

PASS: Real Windows descendants reproduce the original preflight wait beyond its timeout; preflight, guarded ADB, version checks, shared-server startup and MuMu input now return while those descendants remain alive. Successful and failed command exits retain their outcomes. Output channels, binary data, text newlines and Python UTF-8 mode retain subprocess behavior. Process creation follows the operating system's interruptibility. Incident attribution remains unconfirmed without the report host's DEBUG log.
