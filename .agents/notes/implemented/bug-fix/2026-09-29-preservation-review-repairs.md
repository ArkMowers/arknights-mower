---
title: Preservation Review Repairs
status: implemented
category: bug-fix
date: 2026-09-29
---

# Preservation Review Repairs

[中文](2026-09-29-preservation-review-repairs.zh.md)

## Contract

- [INV-DIAG-03] Accepted Archive Drain: Shutdown preserves accepted screenshot and archive work until the common flush deadline; work discarded after that deadline is counted and starts no further file writes.
- [INV-DIAG-04] Encoded Recent Cache: With ordinary history disabled, the recent error context retains encoded frames under its count and byte limits; capture submission performs no encoding and pending raw frames remain bounded.
- [INV-DEV-08] Uncertain Input Delivery: ADB input whose transmission or acknowledgement is uncertain fails without automatic command replay; the input boundary reports a structured delivery-unknown failure.

Temporary Preparation resolves ADB inside the fresh startup Recovery Budget before reading or changing display geometry. The resolved path belongs to the session copy; the persisted Device Profile is unchanged. Readiness and helper initialization use the same deadline.

An explicit same-serial change from a manual preset to a physical preset saves the new identity before the authorized endpoint. Failure retains the last successful saved state and prevents startup. The ordinary target-clearance rule remains active.

The advanced device form exposes the existing launch protection interval separately from the overall Recovery Budget and local observation window. Its persisted value remains `simulator.wait_time`.

## Verification

Offline regressions exercise real RGB submission, accepted archive work during shutdown, deadline exhaustion, ADB resolution before preparation, same-serial identity changes and acknowledgement timeout after an input command is sent. Existing performance and OTA tests use current device interfaces and host-appropriate executable names while retaining their behavior assertions.

The shutdown regressions include slow encoding, lock acquisition, capacity checks and directory creation. Due log snapshots drain within the same deadline; future snapshots resume from their persisted event manifests after restart. An operating-system write already in progress may finish after the deadline. Resolution failures report the current startup error without reusing an earlier preflight result.

The [boundary simplification](../simplification/2026-09-29-preservation-repair-boundaries.md) preserves existing ownership. No configuration schema or glossary term changes.
