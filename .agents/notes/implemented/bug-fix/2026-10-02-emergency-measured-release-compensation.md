---
title: Intelligent Rescue Measured Release and Compensation
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Measured Release and Compensation

## Contract

[INV-SCHED-03] rebuilds strict personal-limit releases after every completed room observation, before checking the next operation budget. Newly measured completion or countdown deadlines take effect within the current observation batch. Final handoff retains occupant-matched release responsibilities while the normal plan is restored. A newer observed deadline replaces the saved deadline; a changed occupant never inherits it.

[INV-SCHED-04] converts overdue started order runs into original-roster restoration after fifteen minutes. Restoration includes vacant slots, retains original-worker reservations, survives unrelated timeout queue rebuilding and waits when another facility occupies a worker. Unstarted overdue order runs retain ordinary expiry handling. Restoration does not repeat insertion or drone acceleration.

## Simplification

The rescue room reader and frozen metadata planner share existing strict-release generation. Compensation remains on the existing task, using the observed original roster and existing restoration executor; no retry wrapper, compatibility path or new setting is introduced. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the interface guarantees.

## Verification

Offline tests exercise real countdown conversion and release generation, initially unknown deadlines, measured completion and handoff deadline replacement. Real order arrangement and virtual time exercise acceleration failures, sixteen-minute and multi-day expiry, vacant original slots, unrelated queue rebuilding and occupied-worker restoration. Device and persistence boundaries remain isolated.

## Review

Standards Findings: shared release generation and existing restoration tasks preserve strict timing and compensation lifecycles.

Spec Findings: a completed room observation cannot consume another room's allowance before newly discovered releases are scheduled; expired started runs retain original staffing restoration without reinsertion. Default full-mood managers remain able to yield beds and explicit higher priorities remain effective.

Fifteen targeted offline suites pass 659 tests and 10 subtests after note promotion. Scoped Ruff, formatting, whitespace and all governance gates pass. A fresh independent conversation reviews the immutable commit before publication.
