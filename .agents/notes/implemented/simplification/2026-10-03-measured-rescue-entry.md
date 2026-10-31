---
title: Measured Intelligent Rescue Entry
status: implemented
category: simplification
date: 2026-10-03
---

# Measured Intelligent Rescue Entry

## Contract

[INV-SCHED-09] permits intelligent rescue entry after initialization reads and effective schedule reconciliation when primaries in at least two distinct recovery groups have measured mood strictly below their personal rescue thresholds, at least one primary is waiting to rest, and current native rotation cannot admit the waiting primaries. Bound schedule groups count once; ungrouped primaries count individually. Resting groups below their rescue thresholds count toward recovery contention. Estimated or predicted readings do not establish entry. Existing episodes reconcile actual rooms on restart; runtime ticks do not start another episode.

The current-only mode of `native_opportunity` uses the existing complete-group replacement and ordinary bed planner on isolated snapshots. It considers immediately executable rotation arrangements and already-due concrete tasks, including charges with measured full-mood Fiammetta, without future event traversal, recovery timers or depletion rates. Due plans preserve measured mood instead of assuming completion. Ordinary current releases require measured completion. Due strict personal-limit releases retain their operation-time allowance before the limit is reached and reuse dispatch validation of resident identity, bed and current configuration; each Fiammetta charge consumes its projected mood before another task can use it. Position mismatches and arrangement retries do not establish a charge opportunity. Full measured dormitory residents with no recovery timer and measured zero-mood workers with zero depletion retain their known state. A planning exception or exhausted search budget remains an incomplete check, rather than evidence of infeasibility. Disabled assistance and feasible native rotation do not dispatch temporary staffing.

History remains available for recovery targets and observation timing. Temporary worker eligibility, individual bed allocation, measured standby, backup freezing, specialized tasks and final handoff retain their existing contracts.

## Simplification

Entry is the only production caller of rescue-line deadlines, injected history rates and earliest-eligibility search parameters. Removing entry prediction removes those unused parameters and their event generation. The existing projection gains a current-only mode instead of duplicating the native planner. Search completeness depends on remaining work and observed exceptions, not a temporary queue-size comparison that can remain latched after the queue drains.

## Verification

Offline tests distinguish one bound group from multiple independent recovery groups, available native capacity from competing beds, and low resting groups from completed residents. They reproduce measured zero and low primary mood with full dormitory residents whose completion timers are absent. Controls cover native feasibility without rates, due returns and executable charges that preserve native rotation, future tasks that cannot postpone current entry, unreadable and predicted mood, equality at the threshold, disabled assistance and restart reconciliation. Projection tests preserve the source operators, beds, plans and tasks. Historical target and final handoff tests retain their existing assertions. A strict-release regression uses the real operation-time scheduler and dispatch guard: a resident at mood 10 with personal limit 12 can release a bed when due, while future tasks, changed limits, removed limits and mismatched beds do not prove current capacity. The ordinary-release control still requires completion, and all cases preserve source operators, beds and tasks.

## Review

Standards Findings: PASS at immutable implementation commit `e113afa7`. The independent review verifies isolated mutable state, shared read-only evaluation, bounded search and governance. Focused implementation tests pass with 286 cases and 4 subtests. Independent verification passes with 719 backend cases and 4 subtests, 10 additional boundary cases and 61 frontend cases.

Spec Findings: PASS. The strict personal-limit release correction passes 369 focused tests; its six dispatch-parity cases reproduce the valid due-release failure before the correction and pass afterward. The independent review verifies measured multigroup contention, executable due releases and one-use Fiammetta charges, with historical targets and handoff retained. The measured-entry glossary replacement and exact group-contention qualification are approved and synchronized.
