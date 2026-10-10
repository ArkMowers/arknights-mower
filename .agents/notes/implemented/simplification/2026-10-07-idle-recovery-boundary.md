---
title: Idle Recovery Boundary
status: implemented
category: simplification
date: 2026-10-07
---

# Idle Recovery Boundary

## Contract

Device failures during idle wakeup leave the MAA task error boundary and return to the existing Device Control recovery entry. Pending scheduler tasks and uncertain-input pauses remain preserved.

## Simplification audit

`maa_plan_solver` has one successful idle handoff inside its MAA exception handler. The handoff repeats the outer scheduler's device-error responsibility. Moving that call after the MAA handler removes the duplicated routing without adding a recovery wrapper, retry policy or exception classifier. Genuine initialization, task submission and MAA execution failures retain their notifications.

## Verification

Offline tests inject an original missing-device exception after successful readiness recovery. Idle failures escape without a MAA notification; genuine MAA failures retain notifications. Classified device errors and cancellation preserve their existing behavior.
