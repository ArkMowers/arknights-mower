---
title: Admission Preemption and Vacant Recovery
status: implemented
category: bug-fix
date: 2026-10-06
---

# Admission Preemption and Vacant Recovery

## Contract

[INV-SCHED-20] distinguishes existing targets from new arrivals using actual occupancy before the arrangement. A newly projected target is still an arrival. New arrivals can preempt strictly lower-priority targets. A displaced target continues competing against subsequent strictly lower-priority targets, stopping after reaching an empty target or exhausting eligible targets. Equal tiers never preempt, even for a larger mood deficit.

Existing targets do not proactively reorder. Ordinary vacancies use eligible non-target residents and arrivals, ranked by tier, locality and mood deficit. Crafting order applies only within eligible equal-tier, equal-locality candidates. Reservations, exclusions, mandatory limits and actual occupancy remain authoritative.

## Implementation

The shared projection performs arrival-driven preemption before filling remaining vacancies. Each target assigned by the chain is excluded from vacancy filling. A preemption chain may span more than two dormitories; vacancy-only filling retains its one- or two-room bound. A target without a lower-tier recipient remains in the displaced bed. No new device reads, tasks or persistent caches are introduced.

## Verification

Focused offline tests cover a three-dormitory chain, arrivals initially planned in a target slot, displaced-target equality despite larger deficit, continuing past equal-tier targets, vacancy locality, reservations and physical recovery setup. The related suites pass 673 tests and 6 subtests; two additional equal-tier chain cases pass in the admission suite. The full-capacity fixture explicitly occupies every bed before testing recovery takeover; a separate vacancy case verifies filling the empty bed without displacing the recovered resident. The focused admission, grouped-dormitory and replacement-coordination suites pass 180 tests.

## Standards Findings

Pass: isolated projection, bounded target traversal, shared priority tiers and occupant preservation. Ruff and repository governance validate the final patch.

## Spec Findings

Pass: higher-tier arrivals immediately obtain recovery targets; existing targets move only through the resulting chain or explicit departure. Equal tiers preserve existing targets. Ordinary vacancies retain the smaller relocation scope.
