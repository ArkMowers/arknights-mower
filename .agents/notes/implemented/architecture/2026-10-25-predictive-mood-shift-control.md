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

### Timeline and selection

Each candidate has exclusive projected operators, a virtual clock and frozen configuration, skills, inventory and maintenance inputs. Old occupants advance to each room-operation completion before new staffing and recovery effects apply. Existing return/release metadata controls resource availability. Forecasts do not invent future inventory, order output, charging or training effects.

Baseline and candidates share participating primary positions and an observation endpoint. Ranking compares waiting after personal floors before legal handoff, ineffective position time, arrangement count, advancement relative to ordinary thresholds, then stable order. Configured zero-mood workers are not ineffective coverage. Early departure must strictly improve one of the first two quantities without worsening a higher-priority one; equal continuity cannot justify leaving early.

For example, A and B share a bed and a cover. A reaches its floor in two hours, B in three. If A can leave now and complete legal recovery and return within one hour, releasing both resources for B, while waiting for A's floor delays B, the earlier departure may win. The forecast must still prove cover endurance and complete subsequent recovery; it does not claim the latest feasible early start or global optimality. Exhausted A cannot use this exception.

A batch includes at most sixteen candidates including baseline, each processing at most sixty-four discrete nodes. Nodes include advances through skill or personal-limit boundaries, room-operation completion and backup transitions; mood queries alone do not count. An attempted sixty-fifth node records exhaustion without further processing. Candidate truncation, baseline exhaustion or any candidate exhaustion stops remaining doomed work and disallows an early decision. Existing legal scheduling continues; an incomplete search does not make the configuration illegal.

Existing rules retain replacement lists and order, groups and multiple bindings, exhaustion, personal limits, full recovery, recovery tiers, protected beds and dorm-isolation preferences, including permitted unavoidable cohabitation. Operators not yet occupying their effective primary positions are reconciled by existing scheduling before prediction uses the new state. Training, crafting, Fiammetta charging and rescue retain their owners.

Projection does not cross a special task with an unproven ending state by inventing resource changes. A backup transition changing participating group identities cannot prove early rest using stale members. Real tasks and timestamps remain; normal execution or actual backup reconciliation supplies the next planning input. These limits reject only unproven early advice and do not block independent legacy work.

### Replanning and execution

Replan after initialization observations, normal room calibration, completed arrangements or specialized actions, and changes to effective plans, skills, personal limits, recovery state or task dependencies. Advancing time without relevant changes reuses absolute deadlines. A new successful same-value observation is new evidence; unchanged failed-task readback creates no timed retry.

One empty `NOT_SPECIFIC` task carries `mood_control_event` and participates only in wake ordering. Its due branch runs in memory before generic room-reading dispatch. Valid due early advice materializes once, and consumed events are not recreated. Disabling, restart or rescue removes prediction-only wakes while actual arrangements, started work and retained failures keep their existing lifecycles.

Before the first physical arrangement, new observations must re-establish early eligibility and timing. Backup convergence that enlarges an arrangement rechecks its operation window. Started arrangements preserve remaining work rather than rebuilding from intermediate occupants. Complete backup convergence carries the same evidence without recursively searching all candidates. Unmaterialized advice and search caches are not persisted; plain-data evidence retained on concrete tasks is revalidated before unstarted execution.

### Performance and simulation

Reuse same-time mood and deadline trajectories. Known-rate current-value queries avoid model copies; target queries stop before calculating post-target skill effects. Each projected arrangement reuses absolute deadlines until staffing changes. Relevant facts determine the input signature, rather than object addresses, elapsed time or a bare model revision.

INFO diagnostics distinguish evaluated candidates, enumerated candidates, processed nodes and arrangement trace events, with total time, model time, reuse and exhaustion. Model time belongs to total time and is not added again to nested backup calculations.

The [income-simulation policy mapping](../../../../docs/subsystems/plan-editor.md#predictive-mood-control-simulation) consumes the same setting; both modes still calculate physical mood. The TypeScript [planning adapter](../../../../ui/src/riic/vendor/scheduler/mowerPredictivePlanning.ts) uses existing matching and recovery owners and shares inputs and expected traces with Python. Compiler and successful reports identify policy version and selection. Historical successful results remain available; missing policy fields do not represent new-policy results. Shared formulas alone do not establish policy parity.

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
