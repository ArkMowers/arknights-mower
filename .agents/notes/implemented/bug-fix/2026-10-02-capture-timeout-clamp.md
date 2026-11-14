---
title: ADB Capture Timeout Preserves Budget
status: implemented
category: bug-fix
date: 2026-10-02
---

# ADB Capture Timeout Preserves Budget

[English](2026-10-02-capture-timeout-clamp.md) | [中文](2026-10-02-capture-timeout-clamp.zh.md)

## Contract

ADB capture shares one monotonic deadline across its guard, SDK query, frame read and decode. Every remaining timeout is bounded by the initial effective capture budget and any parent I/O budget; an expired deadline raises before further I/O.

## Implementation

Floating-point addition and subtraction can produce a remaining timeout slightly above ten seconds when successive clock samples are equal. Clamping to the initial effective budget preserves the configured limit without relaxing assertions. The [Device Control contract](../../../../docs/subsystems/device-control.md) owns shared ADB guarding and finite I/O budgets.

The same rounding also affects session reconnects. `_CommandWindow.remaining` caps the session's local window, and the shared ADB `_remaining` boundary carries the caller's initial budget through probe sockets, explicit stop responses, client-version checks and CLI execution. Both boundaries preserve deadline expiration and elapsed-time deductions.

## Verification

A frozen monotonic clock at the rounding boundary reproduces the Windows compatibility failure. Mocked guard and both raw socket requests preserve order and use timeouts within budget.

Additional fixed-clock regressions reproduce `510.2 + 5 - 510.2 > 5` before repair and verify exact five-second upper bounds for pinned emulator reconnects, version guards, commands and socket operations. Existing regressions retain decreasing timeouts, shared connect/reconnect deadlines and rejection after budget exhaustion. Device and network I/O use substitutes.

## Standards Findings

PASS. Existing domain terms and configuration schemas remain unchanged. Tests isolate device and network operations. Analysis budgets, deadline bounds and caller state preservation retain their contracts.

## Spec Findings

PASS. Focused regressions verify the stated caller behavior and boundary cases. Runtime configuration checks retain their existing failure behavior.
