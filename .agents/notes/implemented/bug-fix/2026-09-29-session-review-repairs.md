---
title: Session Configuration and Recovery Review Repairs
status: implemented
category: bug-fix
date: 2026-09-29
---

# Session Configuration and Recovery Review Repairs

[中文](2026-09-29-session-review-repairs.zh.md)

## Contract

- [INV-01] and [INV-03]: A startup's detected game package and endpoint belong to its session. Failed initialization and unrelated settings saves preserve the user's Device Profile.
- [INV-04] and [INV-UI-01]: An immediate backend edit computes coupled fields against the saved profile. Unconfirmed identity edits remain in the component draft.
- [INV-DEV-03]: Every instance command uses the minimum of its own remaining deadline, the enclosing Recovery Budget and its command limit.
- [INV-DEV-07] Capture Recovery Separation: Normal frames use a fresh per-operation deadline; a degraded ADB backend verifies its bound target without invoking the replaced capture helper.
- [INV-REC-03] Scene Recovery Limit: Repeated scene transition exceptions permit one game restart per navigation call, then raise a recognition failure; cancellation and device failures propagate immediately.

## Boundaries

The device owns the verified runtime selection used by game commands, capture, touch and MAA. The persisted profile remains the source of explicit selections. A recovery transaction retains one deadline through its readiness and capture work.

MuMu idle shutdown disconnects only the endpoint of an owned client. A closed session or released client skips transport cleanup; the saved endpoint never substitutes for a missing runtime target.

Scene navigation reuses the application's device recovery and the solver's game restart. It neither adds simulator lifecycle commands nor retries uncertain input delivery.

The existing glossary definitions of Device Profile, Instance Binding, Readiness Verdict and Recovery Budget cover these repairs. No configuration schema or domain term is added.

## Verification

Offline regression tests cover failed initialization followed by an unrelated save, operation after an expired recovery deadline, ADB capture with an unavailable original helper, decreasing instance-command deadlines, preset round trips with paired backend edits, and scene restart exhaustion.
