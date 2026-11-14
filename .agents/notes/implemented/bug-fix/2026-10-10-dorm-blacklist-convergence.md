---
title: Dormitory Blacklist Convergence
status: implemented
category: bug-fix
date: 2026-10-10
---

# Dormitory Blacklist Convergence

## Contract

[INV-SCHED-13] Dormitory migration and closing-bed allocation reject the excluded recovery tier, including current and displaced residents. Rejected residents remain in the allocator's departure result so callers release the original bed or restore working primaries. Group confirmation discards excluded dynamic recovery targets under the effective policy; all other named targets still require observed occupancy. Fixed dormitory roles and specialized Fiammetta assignments retain their existing boundaries.

## Cause and implementation

The supplied log records Proviso resting in dormitory four, followed by a backup migration requesting Proviso in dormitory three. The user confirms Proviso belongs to the global dormitory blacklist. The migration ranks excluded residents last but admits them when capacity remains. Execution rejects Proviso and selects Swire, while group confirmation retains Proviso and recreates the same task. A cached roster match skips subsequent arrangements.

The shared recovery allocator excludes this tier before capacity admission and retains rejected candidates for existing departure handling. Completion applies the same tier and dynamic-position predicates before checking required occupants, including pending targets restored from an earlier task. Eligible targets and unrelated facility targets remain pending until observed.

## Simplification

The shared allocator has migration and closing-bed callers, both requiring the same admission boundary. Completion already reconciles targets with effective training protection. These existing boundaries own the repair; no candidate service, state field, configuration setting or retry mechanism is added. Pre-flight review identifies no independent abstraction to remove.

## Verification

Offline regression cases reproduce migration from current beds, preserved snapshots and displaced beds in both ordering modes, workaholic exclusion, closing beds and stale group-confirmation targets after replacement. Fixed dormitory and eligible recovery targets remain subject to observation. The initial twenty-case reproduction fails seventeen cases and passes three controls before the repair. The final regression file contains twenty-five cases, adding workaholic completion and ordinary measured-zero-mood eligibility. Nine focused scheduling and governance files pass 441 tests against alpha `62cb6bc8`. Ruff, formatting and structural governance pass; governance retains two historical archived-reference warnings, and legacy configuration migration emits two existing Pydantic serializer warnings. Verification uses offline state and simulated observations, without live device input.

## Standards Findings

PASS. The two production changes reuse the shared tier classifier, allocator departure handling and group-completion reconciliation. No persisted fields, settings, device operations or retry mechanisms are added. All code-symbol references resolve and the focused checks pass. Concept-impact review preserves the meanings of dormitory priority, dynamic Free slots and actual/projected occupancy; no glossary change is required.

## Spec Findings

PASS. Excluded residents cannot consume migration or closing-bed capacity even with spare beds or existing single-target recovery. Their original beds receive departure handling. Old excluded recovery goals cannot requeue, while unobserved working targets, fixed dormitory roles and eligible recovery targets remain pending. Ordinary measured-zero-mood residents retain their recovery bed and deadline. Existing group and training-protection regressions pass.
