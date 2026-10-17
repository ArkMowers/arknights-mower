---
title: Simulator Command Isolation and Review Repairs
status: implemented
category: bug-fix
date: 2026-09-29
---

# Simulator Command Isolation and Review Repairs

[中文](2026-09-29-review-command-isolation.zh.md)

## Contract

- [INV-DEV-02] Lifecycle Command Isolation: Simulator lifecycle commands pass literal argument lists without a shell and act only on an explicitly identified instance; unavailable instance control fails without a host-wide action.
- Retired MuMu 6 selections have no registered discovery or lifecycle adapter, and the legacy command builder rejects that product.
- MuMu IPC gestures preserve one touch sequence across segments. MuMu manager matching requires an explicit index or unique name, validates both when supplied, and rejects ambiguous identity or invalid ports.
- Settings pauses periodic status queries while hidden, compares profile values independently of key order, and retains synchronous autosave dependency tracking.

## Verification

Offline regression tests cover gestures, literal command arguments, refusal of unverified lifecycle actions, JSON identity ambiguity, endpoint aliases, and configuration boundaries. Existing targeted device, scheduler initialization, WebSocket, and frontend tests verify compatibility.

The [simplification audit](../simplification/2026-09-29-review-boundaries.md) records retained mechanisms. The [device subsystem](../../../../docs/subsystems/device-control.md) owns the permanent invariant. No glossary definition changes.
