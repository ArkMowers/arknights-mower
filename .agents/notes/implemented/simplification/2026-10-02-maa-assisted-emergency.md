---
title: MAA Assisted Emergency Recovery
status: implemented
category: simplification
date: 2026-10-02
---

# MAA Assisted Emergency Recovery

## Contract

[INV-SCHED-09] separates native rescue from optional MAA assistance. `maa_emergency_infrast_enable` defaults to disabled. Native rescue retains average-mood evaluation, complete replacement matching, shared dormitory candidates and ordinary rotation. AST migration removes actual `op_data.rescue_needed()` backup calls, preserves other backups and backs up the original configuration. Snapshot migration removes obsolete derived shifts and retains specialized tasks; identifiable condition vectors follow backup names or migrated indices.

Initialization reads actual occupancy and measured facility mood before evaluating backups and native feasibility, including cached startup. A required primary below `lower + (upper - lower) * resting_threshold * rescue_threshold`, or projected by compatible history to cross that line before recovery, requires a complete blocked native projection before assistance starts. The default rescue line is 11.7. Unknown mood, an isolated failed group and low average mood do not establish blocked native rotation. Bounded projection includes complete cover matching, bed takeover, queued shifts, measured bed releases and committed Fiammetta charges. Budget exhaustion and uncertain timing preserve native rescue. Subsequent runtime checks never start a new episode.

## External Control and Persistence

The episode saves its dispatch marker, frozen backup conditions, dormitory layout, actual temporary roster, targets and target basis before external control. One MAA automatic-efficiency infrastructure task runs per episode. It includes existing working facilities and processing, excludes dormitories, training and assistant changes, disables Fiammetta recovery, drones and replenishment, and leaves manufacturing products unchanged. Its selection threshold is the highest measured pending-primary mood plus one, divided by 24 and capped at one. Operators receive no Fiammetta, training or trade-order selection protection.

MAA has a ten-minute monotonic budget. Mower does not operate the device concurrently or preempt this run for specialized tasks. Accepted start and complete verified callbacks establish external completion; actual room readback reconciles the resulting staffing. Failure, timeout and unknown outcomes remain recorded without retry dispatch. MAA stop is confirmed within a finite cleanup budget before recognition resets and Mower resumes. An unconfirmed stop halts device operations. Restart reconciles actual facilities and never repeats dispatch, including unknown results. Disabling the setting prevents new dispatch while an existing episode finishes its handoff.

## Recovery Scheduling

Backup transitions, ordinary workstation correction, normal shift-off/return, product switches and other MAA work remain paused. Feasible trade-order runs, Fiammetta charging, crafting, mastery and training-support tasks retain their normal eligibility and reservations. Specialized temporary swaps restore the observed temporary roster. MAA occupation of required trade-order operators pauses the run without reclaiming workers. Expired paused order tasks do not retry. Mastery failures report their own cause without ending recovery; crafting reports inventory, recipe, mood or reservation failures specifically.

Ordinary order and manufacturing-product collection remains independent of order runs and mood observations at a fifteen-minute cadence. The existing collection entry performs no staff changes, product switches or backup evaluation. A collection deadline wakes the scheduler before a longer mood-check interval. MAA holds exclusive device control until stopped; overdue collection runs after control returns. Active specialized tasks and their compensation complete before handoff.

All dormitory positions become runtime Free beds except Fiammetta's configured position. Shared recovery tiers apply without promoting backup primaries or protecting ordinary fillers and crafters. Higher-priority arrivals can displace lower-priority residents, including standby operators. Required recovery uses all available beds in batches; operators already at their measured targets do not reacquire beds. Dorm managers return across dormitories at slot one before slot two, without displacing unfinished required recovery or borrowing workers from MAA facilities. Shared candidate estimates and reservations remain authoritative for ordinary admission; missing primary readings require actual verification before return.

## Historical Targets and Handoff

`agent_action` adds nullable environment keys and slot indices. Each model consumes at most 200 measured observations from fourteen days. Compatible continuous-environment segments span ten minutes to twelve hours and require at least three usable segments. Work consumption uses the seventy-fifth percentile; recovery uses the twenty-fifth percentile. Facility transitions, full/zero platforms, crafting and charge jumps do not form natural slopes. Unidentified legacy environments do not establish a rate. Actual work/charge cycles remain individual, including Gladiia's own consumption and feasible charging appointments.

A target combines the native retained-mood rule, expected consumption until the next usable recovery opportunity and the larger of one mood point or fifteen minutes of consumption. Insufficient history uses the normal shift-off line plus one, capped at the individual's upper limit. An over-limit historical cycle requests an earlier proven native rotation instead of truncating the target. Predictions schedule checks only: absent recovery speed checks every fifteen minutes; measured speed schedules within five to thirty minutes. Room reads merge related observations. Staffing changes invalidate their environment keys without invalidating unrelated candidates.

Actual primary mood must satisfy every required target. Native complete matching and beds must permit each next normal group recovery, and specialized compensation must finish before exit. Handoff reevaluates backups, restores work facilities and managers together, reads actual staffing and then resumes ordinary scheduling and fresh order planning. Pending handoff plans and selected conditions survive partial failure or restart; retries do not dispatch MAA. No fixed duration, majority completion, zero-mood entry or mandatory full-recovery episode remains.

## Simplification Evidence

The cross-cutting rescue condition, majority latch, forced-full targets and concentrated-recovery crafting protection are removed. `EmergencyRecoveryMixin` owns one external-control lifecycle; the existing native planner and shared candidate/tier predicates retain replacement and bed eligibility. History extends existing action records rather than adding another mood cache. Ordinary vacancy-fill validation now applies without a rescue flag.

## Verification

Focused offline suites cover rescue-line entry, uncertain native opportunities, card-estimate isolation, one dispatch and restart, callback and cleanup failures, independent collection wakeups, occupied order operators, frozen ordinary staffing, actual target readiness, partial handoff, shared priority and manager beds, historical environment and charge separation, configuration/task migration and the independent frontend setting. Device and MAA operations use test doubles. No emulator integration runs.

The 55 focused Python suites pass 1,795 tests and 36 subtests. The seven frontend suites pass 66 tests; the production build, Ruff, Prettier and three governance gates pass.

## Standards Findings

The lifecycle retains finite external-control budgets, verified cleanup, measured/estimated separation and isolated native projection. Glossary synchronization remains a separately approved edit under the root agent directives.

## Spec Findings

The assisted episode preserves ordinary collection and specialized tasks while freezing ordinary rotations. Readiness requires actual mood and feasible native recovery; persisted dispatch and handoff prevent repeated MAA staffing.
