---
title: Incomplete Backup Validation Permits Startup
status: implemented
category: feature
date: 2026-10-02
---

# Incomplete Backup Validation Permits Startup

[English](2026-10-02-backup-validation-warning.md) | [中文](2026-10-02-backup-validation-warning.zh.md)

## Contract

Budget exhaustion returns `status: incomplete` and `success: false`; it never claims complete validation. Manual validation displays a warning and startup logs that warning and continues. Ownership and baseline failures, confirmed merged-plan conflicts and unexpected analysis errors remain blocking. Runtime merged-plan checks and convergence guards remain active.

## Implementation

A specific budget exception separates admitted incomplete coverage from other errors. Existing success/message callers retain their Boolean semantics; status-aware startup and UI callers distinguish incomplete coverage. Known facility-product equality conditions share one symbolic state per room, including unlisted values. Unknown conditions remain conservative. The [Scheduling Plan contract](../../../../docs/subsystems/base-scheduler.md) and [coverage decision](../../implemented/bug-fix/2026-10-02-backup-validation-coverage.md) define configuration coverage.

## Simplification audit

One exception type identifies the two budget exits; callers do not parse translated error strings or duplicate analysis. No persistent skip-validation option or second validator is introduced.

## Verification

Hermetic tests cover both budget warnings, blocking baseline and ownership errors, unexpected exceptions, real scheduler entry after a warning, runtime rejection after incomplete preflight, and product-specific mutual exclusion.

## Standards Findings

PASS. Existing domain terms and configuration schemas remain unchanged. Tests isolate device and network operations. Analysis budgets, deadline bounds and caller state preservation retain their contracts.

## Spec Findings

PASS. Focused regressions verify the stated caller behavior and boundary cases. Runtime configuration checks retain their existing failure behavior.
