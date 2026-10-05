---
title: MAA Core Generation Validation
status: implemented
category: bug-fix
date: 2026-10-05
---

# MAA Core Generation Validation

## Contract

[INV-UPD-02] validates desktop core identity and version before connection. The [MAA runtime contract](../../../../docs/subsystems/maa-runtime.md) owns initialization and failure behavior. A changed process-resident core requires a Mower process restart; resource-only changes retain ordinary loading. Native handles and callbacks are not forcibly unloaded.

## Simplification

The scheduler's single-call nested construction wrapper delegates to one tested loader under the existing update transaction. The loader uses existing file identity, independent version probing and verified-instance APIs. It introduces no configuration flags, recovery workers or scheduling state.

## Verification

Offline regressions cover stale initial images, external replacement with unchanged version strings, changes during probing, failed resource loading, failed probing, unchanged-core reuse, resource-only updates, busy instances, missing libraries and SDK reimport after managed updates. Private runtime tracking remains outside the public patch.

## Standards Findings

Pass: native ownership remains with the SDK, device transport and Scheduling Plans remain unchanged, and generation state occupies one entry per SDK class. Focused suites pass 172 tests and 25 subtests. Governance gates pass. Independent native initialization accepts the configured theme without acquiring a device connection or starting tasks.

## Spec Findings

Pass: actual and independently probed disk versions match before connection; external core changes fail before resource loading. Restart guidance distinguishes a process restart from an automation-task restart. No native unload or automatic application restart is added.
