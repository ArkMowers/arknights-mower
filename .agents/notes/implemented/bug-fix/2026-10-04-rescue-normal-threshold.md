---
title: Rescue normal threshold
status: implemented
category: bug-fix
date: 2026-10-04
---

# Rescue normal threshold

## Contract and simplification

[INV-SCHED-09] uses the normal shift-off threshold as the insufficient-history recovery target, without an additional mood point. Existing episodes recompute unfinished fallback targets through the shared target updater. Full-rest requirements retain personal mood caps; history-derived targets retain their existing calculation. Measured recovery and feasible native rotation still govern handoff under [INV-SCHED-03].

The shared target function owns this rule; no configuration, migration or separate exit threshold is added.

## Verification and review

Focused offline tests cover fallback calculation, existing target refresh, release at the exact normal threshold, full-rest requirements and infeasible history-derived targets. Standards review preserves shared planning; specification review preserves measured handoff and complete replacement matching.
