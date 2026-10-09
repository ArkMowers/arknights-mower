---
title: Connection Resource Observation
status: implemented
category: feature
date: 2026-10-09
---

# Connection Resource Observation

[中文](2026-10-09-connection-performance.zh.md)

## Contract

[INV-DEV-23] Performance Observation Isolation: Connection testing reads resource information only from its verified ready target through bounded read-only commands; unavailable information preserves readiness, cancellation propagates, and resource readings never recommend or modify modes or timing settings.

The connection form contains the existing performance selector. Android retains the selector beside its managed-connection notice. After target and boot verification, preflight reads online CPU ranges and `MemTotal` in one guarded ADB shell command with a three-second maximum inside any caller Recovery Budget. Invalid or unavailable readings produce an `unavailable` performance observation. The observation remains transient and target edits clear its display. Ordinary ADB calls resolve the default command timeout at invocation time; the performance query supplies its explicit three-second maximum.

The preflight payload and UI expose CPU and memory as information only, without deriving any recommended mode from those values. The independent [game performance test](2026-10-10-game-performance-test.md) supplies the user-adopted recommendation. Existing automatic feedback policy and numeric timing settings remain unchanged.

## Simplification Audit

The settings page owns one performance selector and one mode update handler. Device preflight already verifies target identity and boot readiness, and its I/O adapter already supplies guarded ADB and deadline propagation. Read-only resource observation reuses these boundaries without another endpoint or persisted hardware cache. A shared component serves the desktop connection form and Android settings without duplicating selection behavior. The independent game test owns input trials and their worker admission.

## Verification

Offline tests cover CPU range parsing, resource-only payloads across small and large device configurations, pinned ADB arguments, bounded execution, unavailable readings, readiness and cancellation isolation, informational UI display, Android restrictions, and stale observation clearance. Existing performance tests verify automatic selection and timing preservation. The game test decision owns explicit adoption evidence.

Verification against alpha base `9021f4de` passes 161 focused Python cases, 182 focused frontend cases, the frontend production build, changed-file Ruff and ESLint checks, formatting and the governance structure checks. Governance retains two historical archived-reference warnings. That initial resource-observation verification uses offline adapters. The game test decision records subsequent live simulator verification.

Default-timeout regression tests override the command budget after module import and verify the actual ADB runner arguments, while explicit performance limits retain their values. The existing inherited-output process regression verifies that a one-second timeout returns without waiting for a descendant holding the output streams.

The timeout repair passes 138 focused cases across command ownership, device performance, preflight, preflight I/O and settings HTTP routes, plus changed-file Ruff checks and governance structure checks. The inherited-output failure and the deterministic default-budget case both reproduce before the repair and pass afterward.
