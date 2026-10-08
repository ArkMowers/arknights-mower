---
title: Shared Priority Admission
status: implemented
category: simplification
date: 2026-10-08
---

# Shared Priority Admission

## Contract

[INV-SCHED-36] applies one admission cursor to trade orders and enabled mastery handoffs. Queued operations, future waiting and prior critical operations count once. Ordinary staffing retains independent executable components; workshop batches before the same critical task admit or defer together. Strict mood releases and task phase state retain their protection.

## Caller Evidence

`scheduling` and solver dispatch call `protect_priority_tasks`. The removed `_defer_work_before_swap` scan uses fixed room times and skips prior critical occupancy. The shared admission loop replaces that scan and retains mastery advancement without changing trade order task times. Existing Actual and Projected Occupancy terms cover the change; no glossary edits are required.

## Impact

The shared budget includes observed slow work facilities, mixed dormitory plans, scheduled waiting and deferred backlog. Admission preserves task identity, dependent suffix order and isolated occupancy projection. Accelerated ordinary work retains its trade-order boundary and yields before mastery handoffs.

## Verification

Paired offline cases compare trade orders and mastery handoffs for measured work budgets, independent components, group atomicity, workshop batches, exact boundaries, waiting and multiple critical tasks. Existing mastery collision, strict release, dormitory continuation and governance suites verify protected behavior.

## Standards Findings

Pass: three invariant registrations, bounded timing samples, Actual Occupancy isolation and bilingual note governance remain consistent. No dependencies, configuration fields or persistent state are added.

## Spec Findings

Pass: 21 targeted offline suites cover 581 tests and 21 subtests, including 58 admission regression cases. Mastery collisions retain trade order times and due-handoff precedence. Work uses the shared 15-second margin; dormitory work retains one minute. Older fixed-budget staffing assertions use the shared admission behavior. Ruff lint, changed-file formatting and whitespace checks pass.
