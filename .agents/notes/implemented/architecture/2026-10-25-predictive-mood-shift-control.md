---
format: decision
title: Coordinate Ordinary Shifts with Mood Prediction
status: implemented
category: architecture
date: 2026-10-25
---

# Coordinate Ordinary Shifts with Mood Prediction

## Problem

The user wants “实时心情计算调控” to coordinate departures and returns from predicted working and recovery time, reducing subsequent cover and bed conflicts. Ordinary primaries may leave early for rotation continuity; explicitly exhausted departures must retain personal floors.

Existing scheduling already predicts exhaustion, working-cover floors, returns and personal-cap releases. The missing capability is comparing ordinary threshold departures with earlier rest on one timeline, including subsequent covers, beds and operation windows. A currently legal bed and cover assignment does not prove that the following group can leave on time.

The [Arknights Mower Base Scheduler subsystem description](../../../../docs/subsystems/base-scheduler.md#predictive-mood-control) owns current behavior. The [shared mood-formula decision](2026-10-25-shared-runtime-mood-engine.md) retains model and runtime ownership. This decision selects ordinary shift timing without replacing formulas or the physical arrangement executor.

## Decision

Use bounded event projection and submit only the next executable arrangement to the existing task system. Enabling “实时心情计算调控” selects both calculated mood and predictive ordinary rotation; disabling restores existing recognition and rotation policy. The advanced plan-editor setting retains `test_mood_calculation`, its false default and transfer format, without a separate toggle.

[`predictive_mood_control.py`](../../../../arknights_mower/utils/predictive_mood_control.py) owns candidate comparison, input reuse and memory-only wakes. Actual arrangements still use existing matching, recovery metadata and complete backup convergence. Advice reserves no operators or beds; concrete admitted tasks own reservations.

### Reasons for bounded comparison

An arrangement that is legal now can occupy the only bed or replacement needed by another group later. Comparing candidates on the same timeline exposes this conflict. For example, A and B share one bed and one replacement: if resting A now lets A return before B reaches its lower limit, waiting for A's normal departure can delay B. This motivates continuity as the first selection criterion; it does not establish a globally optimal schedule.

The [predictive shift contract](../../../../docs/subsystems/base-scheduler.md#predictive-mood-control) owns candidate admission, ordering, budgets, observation invalidation and wake handling. Keeping those rules with the scheduler avoids maintaining a second operational specification in this decision record. Unsupported future effects and incomplete forecasts remain reasons to retain the existing policy, rather than inventing resource availability.

Reusing the existing matcher and recovery metadata keeps early timing subject to the same resource constraints as normal shifts. Isolated projections permit comparing alternatives without reserving real beds. The [simulation policy mapping](../../../../docs/subsystems/plan-editor.md#predictive-mood-control-simulation) shares the decision constraints; equal formulas or equal final income alone cannot establish scheduling parity.

## Alternatives considered

- Improve predictions while retaining existing thresholds and queues: smaller change, but cannot compare future use of shared covers and beds.
- Wait for every personal floor: easy to explain, but contradicts early ordinary rest; retain it for explicit exhaustion.
- Optimize several days globally: observations, backups, skill boundaries and device timing invalidate arrangements and make search difficult to bound. Finite rolling comparison accepts lack of global optimality.
- Add an independent control toggle: separates calculation and policy but multiplies settings and contradicts the selected combined setting. Reuse the saved key.

## Consequences

Ordinary thresholds become the enabled-mode baseline, and fully legal earlier arrangements may improve subsequent continuity. Not every schedule receives early advice. Many occupant skill boundaries can exhaust the node budget quickly, preserving existing policy. Real samples may justify future budget calibration; coverage alone does not justify unbounded expansion.

Missing skill rules, full-growth assumptions for uncached operators, full dorm atmosphere, operation timing and observation errors can alter results. Continuous operation is not guaranteed for every configuration, and unproven improvement is not an illegal configuration. Disabling does not undo physical arrangements; real unfinished tasks retain recovery obligations while prediction caches are disposable.

Mood, personal limits, Actual Occupancy, Projected Occupancy, replacements, groups and recovery targets retain their existing meanings. This adds timing selection and projection flow without glossary changes.

## Verification

[Production planner and dispatch tests](../../../../arknights_mower/tests/predictive_mood_control_tests.py) and [simulation planning tests](../../../../ui/src/riic/vendor/scheduler/mowerPredictivePlanning.spec.ts) cover early shared-resource rotation, exhausted and nonzero floors, insufficient recovery, full recovery, first-observation revalidation, future advice execution, retained tasks and budget fallback. Shared scenarios exercise real planning paths and compare decisions, event times and boundary budgets, rather than only helpers or final income.

[Model query tests](../../../../arknights_mower/tests/calculated_mood_query_reuse_tests.py) cover same-time reuse, skill boundaries, stopping at targets and virtual-clock isolation. Focused model, recovery-tier, dorm-release, group-recovery, task-metadata and backup-snapshot tests exercise reused paths. Simulation checks also exercise policy selection through real ordinary planning and roster settlement. Frontend compilation, pinned-source validation and document checks establish artifact and structural properties separately from behavior.

A compatible exported instance plan and saved model support desktop offline replay, not a claim of a fully synchronized live snapshot. The synthetic empty-queue replay exhausts the budget without selecting an early departure; cold and reused-input times are measured separately. Original-queue replay preserves task identities, timestamps and fields. The change report carries actual timings; they exclude navigation and device waiting and do not establish phone latency, concurrent-instance performance or improved real income.
