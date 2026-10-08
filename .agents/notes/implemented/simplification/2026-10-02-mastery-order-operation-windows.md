---
title: Mastery Order Operation Windows
status: implemented
category: simplification
date: 2026-10-02
---

# Mastery Order Operation Windows

## Contract

[INV-SCHED-17] preserves trade order task times and advances conflicting mastery handoffs. The [subsystem contract](../../../../docs/subsystems/base-scheduler.md) owns the timing and dispatch rules.

## Simplification Evidence

`_support_swap_gap` has three production callers in the previous scheduler. It supplies a symmetric ten-minute minimum to order collision checks, Drone Acceleration eligibility and post-handoff deferral, and also controls ordinary dormitory filling. The scheduler removes this helper and its order deferral rule. Existing entry delays and per-room operation allowances determine conflicts; ordinary filling keeps its independent conservative window. The change adds no configuration or timing history.

A conflict advances the handoff and marks its early execution. Planned support execution retains its existing training, slot and candidate verification and does not reschedule an eligible early handoff to the ideal time. Existing glossary definitions remain accurate.

Maintenance avoidance reuses this early-execution boundary and the existing handoff operation allowance. Main-loop budget selection and idle waiting apply protection before choosing their waiting time; otherwise a restored or newly generated handoff can remain asleep until downtime. The complete announced interval governs handoffs because early-login timing does not establish that the server is available. This extension adds no task type, persistent configuration or domain concept.

## Verification

Offline tests cover the reported nine-minute-fifty-four-second window, elapsed countdowns, exact completion and handoff boundaries, configured fractional entry delays independently of order collision spacing, single-pass convergence across multiple orders, repeated planning, multiple handoffs, one-minute training-room handoffs, overdue order dispatch, cleanup tasks and Drone Acceleration interruption. Planned execution tests distinguish ordinary timing from early execution and retain insufficient-training rejection.

`mastery_maintenance_tests.py` covers both dispatch entries, maintenance boundaries and the final half hour, late announcements, disabled mastery, missing announcements, operation budgets, repeated planning, snapshot restoration, ordinary-task admission, unchanged order acceleration, main-loop daily-work admission, idle waiting and actual support execution without ideal-time requeueing. Tests isolate configuration and application data and replace device actions and external requests.
