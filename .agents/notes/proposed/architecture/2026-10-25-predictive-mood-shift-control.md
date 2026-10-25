---
format: decision
title: Coordinate ordinary shifts using mood forecasts
status: proposed
category: architecture
date: 2026-10-25
---

# Coordinate ordinary shifts using mood forecasts

## Problem

The user wants “实时心情计算调控” to coordinate work and rest using predicted working and recovery times, reducing last-minute resource waits, repeated calculations and room inspections. The user permits ordinary primaries to leave early when this avoids later cover or bed conflicts, prioritizing rotation continuity. Explicit exhausted-shift operators retain their personal lower limits.

Existing scheduling already uses forecasts. Exhausted primaries and working replacements can reserve personal-floor confirmations; returns and personal-cap releases also have prediction consumers. [`resting()`](../../../../arknights_mower/solvers/base_schedule.py) still primarily chooses departures from current mood margins, ordinary thresholds, desired resting counts and current resources. [`plan_metadata()`](../../../../arknights_mower/utils/scheduler_task.py) owns recovery and return timing. The missing capability is comparing the current arrangement with earlier rest on one timeline of covers, beds and execution windows, rather than another arrangement executor.

The [Arknights Mower Base Scheduling subsystem description](../../../../docs/subsystems/base-scheduler.md) owns current occupancy, projection, group, dormitory and failure behavior. The [shared mood formula decision](../../implemented/architecture/2026-10-25-shared-runtime-mood-engine.md) retains formula and runtime ownership. This independent proposal concerns how forecasts select shift times; it does not replace that decision.

## Proposal

Use bounded event projection from the effective plan, observed calibration and existing tasks. Compare a small set of executable rotation orders and commit only the next actionable arrangement. Later projections remain advisory and do not reserve actual operators or beds. Confirmed operations and observations continuously calibrate subsequent decisions.

This change only renames the setting and records the proposal. The control algorithm below is unimplemented; the new label does not make it active. Keep the setting in Scheduling Plan advanced settings, preserve `test_mood_calculation`, its false default and transfer format. Once implemented, enabling it selects both calculated mood and this ordinary rotation policy; disabling it retains recognition and the existing rotation policy.

### Objectives and boundaries

1. Enforce hard constraints first, then prefer avoiding predicted inability to continue working because of insufficient mood or missing legal relief. Requests already at their personal floors take precedence; early departures cannot take their required resources.
2. With equal continuity, prefer fewer unnecessary early departures and arrangements, then retain valid appointments and existing stable ordering. The first implementation does not optimize weighted income or promise global optimality.
3. Retain effective primaries, replacement lists and order, group and multiple-binding rules, zero-mood workers, personal limits, required full recovery, recovery tiers, bed protection, run-order admission and specialized reservations. Existing standby and support admission remains authoritative; prediction cannot expand candidate lists.
4. Dormitory isolation retains its current preference and permitted same-dorm fallback, rather than becoming an absolute constraint. Training, crafting, physical Fiammetta charging and automatic-rescue entry and exit retain their owners. Ordinary forecasts cannot independently start rescue or operate protected training slots.
5. Ordinary departure thresholds define the baseline. An earlier ordinary departure is allowed only when projection demonstrates better subsequent continuity and a complete legal cover/bed matching. Explicit exhausted operators and groups constrained by them remain ineligible; an ordinary group member cannot bypass an exhaustion requirement.

### Inputs and outputs

Each planning batch uses one time and an immutable input snapshot: effective primary/backup plans, actual occupants and observation provenance, model/skill inputs, personal limits, actual beds and confirmed single-recovery targets, task phases/reservations, known run orders and operation budgets. Model time, predicted mood and actual readings remain distinct.

Event projection needs an explicit virtual clock and an exclusive model: advance the old occupants/rates to each event, apply occupancy changes at the projected completion time of each room operation, then recalculate skill and recovery rates. Same-time release, return and departure dependencies follow existing task ordering; resources cannot be consumed before release. Reused matching, recovery and backup functions must receive the same `now` and configuration snapshot, without modifying the global clock or `config.conf`. Current `project_arrangements()` primarily projects ordered positions and still reads current time internally; repeating it does not create a future timeline. Implementation must add explicit-time parameters or controlled adapters.

The result contains the next justified wake time, proposed departing/returning groups, reasons, operator/slot dependencies, projected recovery/handoff times, and a verdict of proven feasible, insufficient evidence or exhausted projection budget. This is internal return data, not another persisted setting or public interface. Working floors, recovery completion, skill boundaries and known task completion can supply events; unavailable mood or recovery rates cannot create a timed retry.

```text
Calibration, effective plan, existing tasks
  -> isolated projection at one time
  -> compare current policy with feasible early rest
  -> select next action or justified event time
      |-- before execution window: keep advice without real reservations
      `-- within execution window: existing admission and backup convergence
                                    -> existing arrangement execution
                                    -> actual confirmation -> updated forecast
```

### Ordinary departures and returns

Candidates include retaining the current arrangement, following existing departure rules, moving one fully matched ordinary rest group earlier, and departing after an existing legal return releases resources. Each candidate projects how long the working cover can continue, when the resting group may legally return, when beds actually become available and whether handoffs fit around critical tasks. A currently empty bed or predicted return alone is not proof of future resource availability.

Ordinary groups may leave early only with complete covers and legal beds. Returns retain existing recovery targets, full-recovery requirements, group-recovery spread rules and waiting bounds; this proposal does not authorize lower recovery targets. A group without a full-recovery requirement may use an earlier legal return only when existing rules permit it and subsequent work can continue. Mandatory personal-cap release remains independent; leaving a dorm does not itself grant a working position.

Early rest adds no separate mood patrol. Normal arrangement visits read and calibrate mood; exhausted/working-replacement floor confirmation retains its dedicated read only upon predicted arrival at the personal floor. Changed occupants or resources invalidate unstarted advice. Started physical arrangements retain their remaining work and compensation instead of restarting rotation from intermediate occupancy.

An acceptance example, not a measured income result: A and B share one recovery bed and one working cover. A reaches its floor in two hours and B in three. After starting early rest, A can complete a legal return in one hour including A's departure and return operations. B's subsequent departure needs another five minutes and cannot overlap A's use of the shared cover. Assume the cover can sustain both groups' legal recovery intervals, other continuation is feasible, and both candidates are observed through hour four. Waiting for A's floor pushes B's handoff beyond its floor; starting A now instead lets A return in one hour and release both resources for B. Projection may select the latter without claiming the latest or optimal early start. If A requires exhausted departure, it cannot use this early option; other legal resources or an explicitly retained unsatisfied request are required.

### Projection scope and cost

Use a finite rolling search covering each candidate's next departure, legal return and the following group's floor, so an early action cannot merely transfer its conflict to the next group. Compare all participating groups to the same observation endpoint, covering these continuation events within the existing model horizon. Missing a necessary recovery event within that scope means insufficient evidence, not proven continuity.

Compare continuity over fixed participating positions and the same endpoint, first minimizing accumulated waiting seconds of personal-floor requests before legal handoff begins, then accumulated seconds without effective working coverage. The latter includes empty positions and depleted workers that cannot work effectively; configured zero-mood workers are excluded. An exhausted floor starts confirmation rather than requiring completed replacement beforehand; all candidates include the same operation budgets. Ties compare arrangement counts, total departure advancement relative to the baseline, then stable order and valid appointments. An early candidate must strictly improve at least one of the first two quantities without worsening a higher-priority one; equal continuity does not justify early departure.

Rank candidates by existing urgency and stable order, always including the baseline policy. Candidate starts come from now, resource release, legal returns, working floors and event boundaries adjusted by real operation budgets. Re-evaluate across skill or backup boundaries; do not assume linear recovery or bisect an entire interval without establishing monotonicity.

Initial offline budgets are 16 candidates per batch and 64 discrete events per candidate. These are computation bounds, not polling counts or reasons to stop task execution. Future group choices reuse existing deterministic matching instead of enumerating every operator combination. Exhausting the budget preserves a still-valid arrangement; without one, existing legal dispatch continues and reports incomplete optimization rather than infeasibility. Only early-departure candidates require complete continuation evidence.

Reuse mood trajectories and same-time batch queries instead of reconstructing all operators from device state for each group/event. Initially, relevant changes may recompute one bounded batch; avoid a new fine-grained dependency-cache framework. Record total planning time, candidate/event counts, model time, reuse and budget exhaustion without adding overlapping backup and planning durations together. Calibrate production budgets using matched real snapshots; desktop results do not establish phone or concurrent-instance latency.

### Replanning triggers

| Event | Proposed behavior |
| --- | --- |
| Startup/restart initialization observations complete | Rebuild unstarted advice from actual state; preserve started and retained failed tasks |
| New normal observation or completed arrangement, charge or crafting | Update model/resources; coalesce into one planning batch after the operation |
| Effective backup, product, skill stage, personal limit, recovery target or critical reservation changes | Invalidate affected forecasts and verify complete handoffs |
| Reserved event becomes due | Validate the event first; execute a complete arrangement with unchanged inputs, or coalesce one recomputation when skills, resources or prerequisites change |
| Only clock time passes; inputs and next event are unchanged | Reuse deadlines; neither wall time nor a bare model revision invalidates the plan |
| Failed observation or unavailable bed/cover | Preserve original task, timestamp and remaining work; allow other dispatch until relevant observations/resources change |

Computation limits, repeated unchanged dispatch and a failed task's own unchanged readback create no periodic wake. A successful external observation may release a prior read failure, separately from whether shift conditions changed. Actual resource release by other tasks must reopen the dependent request rather than leave it behind a stale cache.

### Integration with existing scheduling

Add a device-free Python planner called from ordinary primary planning in `plan_solver()`. Reuse `Operators.project_arrangements()`, existing cover/bed matching, group recovery and backup convergence, rather than implementing a second resource admission system. Read-only projection must not append real tasks or mutate actual observations, inventory or confirmed single-recovery state.

`plan_metadata()` retains existing return/release lifecycles and receives selected timing/dependencies. Existing exhausted and working-replacement floor tasks retain their identities and owners; the planner consumes and deduplicates their events rather than creating parallel equivalents. One entry replaces unstarted ordinary appointments, so old `resting()` and the new policy cannot independently enqueue departures. Disabled mode keeps the old entry.

Existing `_prepare_ordinary_departure()`, `_ordinary_coordination_needed()` and `_validate_calculated_arrangement()` recheck ordinary thresholds, while `_prepare_shift_cycle()` calls `resting()` on its projection. All these entries must use the same policy admission. Tasks carry plain-data early-departure reasons, input versions and dependencies; only still-valid evidence can relax ordinary soft thresholds and desired-resting-count limits. Exhaustion, full recovery, groups, resources and training protection remain mandatory. New observations before the first physical arrangement require revalidation or replanning, not a permanent bypass flag. Started work retains its obligations. Subsequent rotations inside complete backup projection must use the same policy instead of losing early intent through old filtering.

Use critical-task admission and `_prepare_shift_cycle()` for final validation, with existing room/phase operation budgets. Only when the execution window arrives and dependencies are revalidated does advice become a concrete ordinary task with reservations; changed queued inputs require admission again. The task system remains the sole owner of actual reservations. Advice and search caches are not persisted across restarts; existing tasks and retained state continue through existing snapshots.

The main loop currently derives sleep and idle-work budgets from `find_next_task()`; an internal timestamp alone does not wake it. Reuse an empty-plan `SchedulerTask` with `NOT_SPECIFIC` and plain-data `mood_control_event` metadata, retaining at most the earliest predictive event. It participates in time ordering without operator, slot or bed reservations. Dispatch it through a dedicated in-memory branch before default `NOT_SPECIFIC` mood reading, preventing extra room visits. Include event kind, target, recovery episode, observation-input version and absolute deadline; replace on changed input and consume an expired event once per version. Invalid dependencies require one replanning batch or a specific dependency wait, rather than silent loss or fixed delays. Restart/disabling removes unstarted prediction-only wakes and initialization rebuilds according to the current mode; actual arrangements and retained failed requests remain.

### Income simulation alignment

Income simulation always models mood, but [`mowerAdvancedAssumptions()`](../../../../ui/src/riic/vendor/scheduler/mowerAdvancedSettings.ts) does not currently consume `test_mood_calculation`. Its [ordinary departure implementation](../../../../ui/src/riic/vendor/scheduler/mowerAlphaDormPlanning.ts) and [recovery-task implementation](../../../../ui/src/riic/vendor/scheduler/mowerAlphaMetadata.ts) are separate TypeScript policy code. Shared formulas do not automatically synchronize new control policy.

Implementation must map the existing setting into simulation policy: disabled keeps today's rotation, enabled selects predictive control, while both continue simulating physical mood. Python and TypeScript share scenario inputs and expected event traces, comparing candidate order, task times, resource occupancy and retained failures rather than income alone. Record the policy version and setting, and change simulation cache policy versioning to avoid stale results. Equal snapshot, operation-time and observation assumptions should produce equal policy decisions; actual device differences remain observation-calibrated.

### Implementation sequence

1. Define planning input/output and diagnostic-only execution with baseline traces. This is development instrumentation, not a user setting or game operation.
2. Implement bounded event projection and stable candidate comparison for sufficient resources, shared-resource conflicts and unavailable continuation.
3. Connect dispatch, deadline updates and failure recovery; verify replacement of unstarted advice and retention of started work.
4. Align simulation and configuration mapping; complete cross-implementation traces and real-snapshot performance measurements.
5. Enable the new policy only after offline acceptance, followed by authorized device validation of observation and operation error. Until then, help text describes delivered behavior; add early-rest wording when control is implemented.

## Alternatives considered

- Improve prediction while retaining current thresholds/queues: smaller change, but cannot compare future use of shared covers and beds.
- Wait for every operator's personal floor: simple, but contradicts the selected early-ordinary-rest policy; retain it for explicit exhausted departures.
- Optimize several days globally: observations, backups, skill boundaries and device timing make the schedule fragile and search difficult to bound. Rolling finite search accepts lack of global optimality.
- Add an independent control toggle: separates calculation from policy but conflicts with the user's combined setting name and adds configuration combinations. Reuse the existing key.

## Acceptance criteria

These are planned behavior checks; no new control algorithm tests have been executed for this proposal.

| Scenario | Required observable result |
| --- | --- |
| Shared bed/cover example | Ordinary A can start early with full continuation; exhausted A cannot |
| Zero/nonzero personal floors and groups containing exhausted members | Preserve personal requirements without bypass through ordinary members |
| Locally available rest but blocked following group | Local matching does not prove complete continuation; budget exhaustion reports incomplete evaluation |
| Full recovery, personal-cap release, single recovery, protected beds and dorm isolation | Apply existing rules without forecast-specific exemptions |
| Repeated unchanged dispatch, appointments and advancing time | No repeated full search, duplicate reservations or restarted recovery windows |
| Above-floor observations, changed skill input and successful same-value observations | Calibrate/release read failures appropriately; unchanged self-readback cannot loop |
| Missing beds, read failures, restart and independent tasks | Preserve request/time, execute independent work and resume after actual dependency release |
| Advancing equal inputs to future events and same-time handoffs | Advance old occupancy first, release before reuse, and leave real clock/configuration untouched |
| Predictive wake due, invalidated dependencies, restart or disabling | Use the dedicated in-memory branch without extra patrol; no repeated expired event or lost real request |
| Early task through first-room validation and complete backup projection | All admission entries consume valid policy evidence consistently; old soft thresholds cannot cancel it, while hard limits still apply |
| Partial arrangements, backup cycles and run-order execution windows | Preserve remaining work; do not restart from intermediate occupancy or violate admission |
| Equal Python and TypeScript scenarios | Match decisions, times, reservations and failures; disabled mode preserves existing policy |
| Instance snapshots, nested backups and repeated batches | Report cold/warm time, model calls and peak candidate/event counts without claiming phone/concurrency validation |

Extend [projection consumers](../../../../arknights_mower/tests/mood_calculation_projection_consumers_tests.py), [exhausted confirmation](../../../../arknights_mower/tests/calculated_exhaust_dispatch_tests.py), [replacement thresholds](../../../../arknights_mower/tests/calculated_replacement_threshold_tests.py) and [complete shift convergence](../../../../arknights_mower/tests/shift_backup_convergence_tests.py) with offline scenarios through actual planner/dispatch entries. Add corresponding simulation inputs and expected events. Document checks establish format, links and controlled wording only, not design correctness or implementation.

## Risks

Missing skill rules, full-growth and dorm-atmosphere assumptions, actual operation time and observation error can change continuation. The mood model does not fabricate future inventory, order output or external actions; projection must state its plan/condition assumptions and invalidate them when actual backup conditions change. Retain observation and execution-time admission; no policy guarantees uninterrupted operation for every configuration. Bounded search can miss an existing solution; report unproven improvement rather than rejecting configuration as illegal.

Early rest changes the role of ordinary departure thresholds in enabled mode, requiring help, contract and simulation updates when implemented. Disabling restores the old policy but cannot undo actual arrangements; started and retained failed tasks survive the change. Advice caches are disposable, while real tasks keep execution and recovery obligations.

Operator mood, personal limits, Actual/Projected Occupancy, replacements, groups and recovery targets retain their existing meanings. This proposal adds timing selection and projection flow without glossary edits. It owns the proposed relationship between planning components; the subsystem description retains current behavior. Keep the record proposed until implementation and verification are complete.
