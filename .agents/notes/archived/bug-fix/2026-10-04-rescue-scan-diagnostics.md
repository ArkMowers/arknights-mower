---
title: Rescue Scan Diagnostics
status: archived
category: bug-fix
date: 2026-10-04
---

> Superseded by [Configured Rescue Schedule](../../implemented/simplification/2026-10-04-configured-rescue-schedule.md).

# Rescue Scan Diagnostics

## Contract

[INV-SCHED-09] retains existing selection and dispatch behavior. INFO logs explain snapshot reuse, fallback reasons with at most eight operator names, progress every five pages, completion or interruption, selected workers and staffing blockers. Scanning remains bounded to twenty pages and forty-five seconds. No additional scans or retry tasks are introduced.

## Simplification and Review

Diagnostics use existing scan and matching branches without a separate reporting abstraction. The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) owns selection semantics.

Standards Findings: No outstanding findings. Existing budgets, eligibility and cleanup remain unchanged; diagnostic name output is bounded. Ruff passes.

Spec Findings: No outstanding findings. All 240 focused offline rescue tests pass. Logs distinguish cached selection, physical scanning, interruption, insufficient candidates, matching conflicts and task-window deferral.
