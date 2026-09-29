---
title: Reuse Existing Recovery and Configuration Owners
status: implemented
category: simplification
date: 2026-09-29
---

# Reuse Existing Recovery and Configuration Owners

[中文](2026-09-29-review-recovery-ownership.zh.md)

## Evidence and Contract

`DeviceSettings.edit` is the sole production caller of `editedDevicePatch`. It reuses that helper with the saved profile as its comparison base, preserving backend coupling without copying identity fields from the draft.

`DeviceControl.capture` is the sole caller of `_standard_adb_ready`. Its target check uses the session's existing readiness classification without allocating the replaced screenshot helper. Normal capture does not need the completed recovery transaction's deadline.

`BaseSolver.restart_game` already owns game exit, launch and recognition invalidation. Scene recovery reuses that operation after device recovery instead of adding simulator command dispatch.

The repairs extend these existing owners; they add no configuration proxy, backend registry or generic deadline service. [INV-01], [INV-04], [INV-DEV-07] and [INV-REC-03] remain the verification boundaries.

## Verification

Component tests verify the saved backend pair and unchanged identity. Capture tests verify independent normal deadlines and target checks. Scene tests verify one restart and propagation of terminal failures.
