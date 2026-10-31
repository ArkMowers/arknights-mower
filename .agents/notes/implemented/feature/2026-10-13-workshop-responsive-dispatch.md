---
format: decision
title: Responsive workshop dispatch
status: implemented
category: feature
date: 2026-10-13
---

# Responsive workshop dispatch

Automatic growth crafting responds to committed local inventory changes and admits selected operators with enough known Operator Mood for one batch. The [growth planning contract](../../../../docs/subsystems/growth-planning.md) defines the interfaces and scheduling boundaries; the [planning-path decision](../simplification/2026-10-13-workshop-planning-path.md) records removal of unused generators.

## Problem

Recorded battle drops previously did not request crafting recalculation, and new automatic tasks required mood greater than 22. Users could not distinguish material, mood and reservation blockers; status needs the same eligibility rules as dispatch.

## Decision

A process-local signal coalesces committed stock changes. Ledger writers publish only after commit; MAA callbacks perform no planning or device actions. Startup and successful edits to operator policy request reconciliation. The scheduler consumes the signal at existing safe boundaries, preserving active external control, staffing compensation and imminent tasks. Clearing before computation preserves writes published during computation. A failed recalculation retains the signal and blocks old quotas, including when saving the paused configuration fails.

One local growth projection supplies configuration and status. Ordered cumulative project budgets, protected training reservations, recipe selection and confirmed batch accounting retain authority. Equivalent settings preserve the configuration generation; changed quotas invalidate old automatic tasks. Manual backup and restoration retain their existing lifecycle.

Automatic mastery-source settings require known positive mood sufficient for one recipe batch, including supported mood-cost rules. Ordinary manual admission retains its existing greater-than-22 threshold. Existing reservations, candidate ranking, material protection and specialist allocation remain binding. Missing-only automatic allocation excludes Nine-Colored Deer because it cannot add unrelated fodder.

The authenticated status endpoint reports execution, project, recipe and at most three structured blockers. It reads local observations without configuration writes, task creation, cloud requests or rejection-cache pruning. The growth page refreshes on relevant edits and polls every 15 seconds after completion while visible and running. Requests have a 10-second timeout; late responses are ignored, failures mark retained data stale, and unmount clears polling and cancels requests.

## Verification and scope

The focused backend run passes 830 tests across workshop, growth crafting, MAA/local inventory, emergency reservations and mastery suites. It reports 19 existing Pydantic fixture-serialization warnings. The focused frontend run passes 25 tests across status polling, workshop configuration and growth crafting order. Refresh/status coverage includes failed transactions, duplicate receipts, unknown baselines, concurrent publications, restart, cancellation, failed pause persistence, exact mood boundaries, read-only diagnostics and endpoint authentication.

Validation is offline; no live-device integration is performed. Lower-yield fallback, automatic fodder, switching-cost optimization and random-byproduct reconciliation remain outside this change. The signal is transient; startup reconciliation covers changes across process restart.

## Alternatives considered

Planning directly in drop callbacks brings scheduler responsibilities into external control; existing safe boundaries and a coalesced signal separate these responsibilities. An independent status algorithm duplicates eligibility policy, so diagnostics reuse production checks.

## Consequences

Newly sufficient stock resumes preparation, and workers below the ordinary manual threshold can perform an affordable automatic batch. Smaller batches may increase staff changes. Recalculation failure suspends crafting until data or persistence recovers. The manual configuration backup continues to support restoration after automatic control ends.
