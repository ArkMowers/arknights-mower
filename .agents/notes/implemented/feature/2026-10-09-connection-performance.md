---
title: Connection Performance Recommendation
status: implemented
category: feature
date: 2026-10-09
---

# Connection Performance Recommendation

[中文](2026-10-09-connection-performance.zh.md)

## Contract

[INV-DEV-23] Performance Observation Isolation: Connection testing reads performance information only from its verified ready target through bounded read-only commands; unavailable information preserves readiness, cancellation propagates, and recommendations never change persisted selections or timing settings without a user edit.

The connection form contains the existing performance selector. Android retains the selector beside its managed-connection notice. After target and boot verification, preflight reads online CPU ranges and `MemTotal` in one guarded ADB shell command with a three-second maximum inside any caller Recovery Budget. Invalid or unavailable readings produce an `unavailable` performance observation. The observation remains transient and target edits clear its display. Ordinary ADB calls resolve the default command timeout at invocation time; the performance query supplies its explicit three-second maximum.

The preflight payload retains a resource estimate for compatibility: fewer than two cores or 1792 MiB yields `low`; fewer than four cores or 3584 MiB yields `medium`; other valid readings yield `high`. It uses guest resources, excludes `xhigh` and does not measure game feedback. The current UI displays CPU and memory only. The independent [game performance test](2026-10-10-game-performance-test.md) supplies the user-adopted recommendation. Existing automatic feedback policy and numeric timing settings remain unchanged.

## Simplification Audit

The settings page owns one performance selector and one mode update handler. Device preflight already verifies target identity and boot readiness, and its I/O adapter already supplies guarded ADB and deadline propagation. Read-only resource observation reuses these boundaries without another endpoint or persisted hardware cache. A shared component serves the desktop connection form and Android settings without duplicating selection behavior. The independent game test owns input trials and their worker admission.

## Verification

Offline tests cover CPU range parsing, resource estimates in the payload, pinned ADB arguments, bounded execution, unavailable readings, readiness and cancellation isolation, informational UI display, Android restrictions, and stale observation clearance. Existing performance tests verify automatic selection and timing preservation. The game test decision owns explicit adoption evidence.

Verification against alpha base `9021f4de` passes 161 focused Python cases, 182 focused frontend cases, the frontend production build, changed-file Ruff and ESLint checks, formatting and the governance structure checks. Governance retains two historical archived-reference warnings. Device behavior uses offline adapters; no live simulator test runs.

Default-timeout regression tests override the command budget after module import and verify the actual ADB runner arguments, while explicit performance limits retain their values. The existing inherited-output process regression verifies that a one-second timeout returns without waiting for a descendant holding the output streams.

The timeout repair passes 138 focused cases across command ownership, device performance, preflight, preflight I/O and settings HTTP routes, plus changed-file Ruff checks and governance structure checks. The inherited-output failure and the deterministic default-budget case both reproduce before the repair and pass afterward.
