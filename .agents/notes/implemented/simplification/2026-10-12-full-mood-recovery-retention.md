---
title: Full Mood Recovery Retention
status: implemented
category: simplification
date: 2026-10-12
---

# Full Mood Recovery Retention

## Contract

[INV-SCHED-02] preserves verified full-mood occupants at every position during single-target recovery setup, including group-recovery managers. Unknown mood never qualifies as verified full mood. Actual readback verifies every retained competitor before recording recovery; the target keeps its final position throughout restoration.

## Caller Evidence

`BaseSchedulerSolver.ensure_dorm_recovery_order` is the sole production caller of `recovery_order_plan`. One shared full-mood check replaces position-specific retention and duplicated dormitory-replacement mood checks. No public interface or configuration changes.

## Verification

Offline `dorm_recovery_tests.py` cases cover full-mood replacements and Free occupants, group-recovery manager positions, unknown mood, changed competitor readings and stable target placement. Existing failure and restoration cases remain binding.

## Standards Findings

PASS: Shared mood validity checks preserve unknown-state handling and existing reservations. The change uses existing glossary terms and introduces no configuration or runtime resources. Governance checks pass.

## Spec Findings

PASS: Full-mood occupants retain their positions; unchanged arrangements still read actual mood and the final recovery countdown. Focused recovery, grouped replacement, selection, performance timing and governance suites pass 374 offline tests after adaptation to the current alpha branch.
