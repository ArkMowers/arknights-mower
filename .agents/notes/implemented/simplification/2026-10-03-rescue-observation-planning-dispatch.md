---
title: Rescue Observation and Dispatch Ownership
status: implemented
category: simplification
date: 2026-10-03
---

# Rescue Observation and Dispatch Ownership

## Contract

[INV-SCHED-09] assigns initial observation and admission to startup, and recovery planning to one event-driven dispatch path. A due mood check or completed staffing/specialized task advances planning. Completed staffing is verified against actual residents; unknown rooms retain their pending plan. The next working group is considered after confirmed completion without waiting for the mood-check deadline. Group replacement matching, individual dormitory admission, reserved standby, manager restoration, and measured final handoff retain their existing rules.

Initial card observation includes owned rescue candidates when needed. Temporary staffing reuses valid shared mood observations and Skland skill unlocks. Missing ownership, mood or skill information retains facility-card fallback; actual selection still confirms card mood. Estimates never establish entry or final handoff eligibility. Ordinary exhaustion scheduling stops at the rescue boundary while trade orders and Fiammetta retain normal scheduling.

## Simplification

Startup no longer dispatches a second planning path. Staffing reconciliation, resumable collection/readback and check-task publication have explicit ownership in the existing mixin. The same check-task publisher handles normal and deferred observations. No alternate rescue engine, compatibility schema or additional persistent cache is introduced. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns the invariant.

## Presentation

The task table and task report label rescue staffing, dormitory arrangements, standby release and mood checks. Unchanged room positions remain unchanged; full-room selection logs do not establish that each resident is a newly selected substitute.

## Verification

Offline regressions cover exhaustion suppression, continuation before a future mood check, initial candidate observation, cache reuse, missing-data fallback and rendered task reports. Existing recovery, reservation, restart, priority, specialized compensation and final handoff suites remain authoritative.

## Review

Standards Findings: PASS. Existing observation budgets, cancellation, read-only evaluator sharing, ownership boundaries and glossary terminology remain in force. No persistent compatibility layer or additional observation cache is introduced. Ruff, formatting, diff and governance checks pass.

Spec Findings: PASS. Focused backend suites pass 627 tests and 24 subtests; frontend log/store suites pass 13 tests. The two-group regression applies actual first-group readback, verifies immediate second-group dispatch and confirms that both groups occupy dormitories. Admission-only retests cover removing duplicate target and capacity planning from startup. Tests retain specialized reservations before workshop planning and leave idle ticks without repeated workshop checks. No live-device integration runs are used.
