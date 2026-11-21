---
format: decision
title: Generate main plans with bounded search and income simulation
status: archived
category: feature
date: 2026-11-17
---

# Generate main plans with bounded search and income simulation

## Problem

Operator and combination recommendations do not allocate replacements, recovery beds or shared group bindings. Users need a main Scheduling Plan for their owned operators and current resources. Existing active records do not own candidate generation or its selection boundary.

## Retirement

On 2026-11-17, the user selected the existing Mower AI RIIC skill and withdrew the separate generator button and fixed candidate constructor. The following body preserves the retired prototype and its evidence, not the current entry point. The [existing AI planning decision](../../implemented/feature/2026-10-13-riic-ai-planning.md) owns subsequent planning. Rescue blank-slot inheritance remains under the [scheduler contract](../../../../docs/subsystems/base-scheduler.md#rescue-plan-inheritance).

## Decision

Use bounded candidate construction followed by native validation and the existing income simulator. The [Arknights Mower Scheduling Plan Editor subsystem description](../../../../docs/subsystems/plan-editor.md#ai-plan-generation) owns the input, selection, cancellation and explicit application rules. The generator is executable without an AI model; a skill can explain goals and investigate results but does not provide production formulas or declare validity.

Candidate construction reuses current unlocked skills and shared recommendation data. It considers facility capacity, dedicated replacements, recovery beds, group bindings and charging targets. Existing main plans can supply more complex bindings, but removal of backups requires an independent trial. Primary-versus-replacement contribution proposes Fiammetta targets; whole-plan simulation compares their effects, including a Gladiia-only option. Dedicated replacements avoid exhausting an operator by repeatedly covering independent workplaces. If the roster cannot cover every facility, the result identifies unstaffed facilities rather than inventing operators.

The generation session separates candidate construction and income Workers from the editor. Native validation, calculation and cost reads have deadlines and cancellation. The evaluator checks actual resource accounts and mood observations. A manufacturing wait counter alone is insufficient evidence of a material shortage: empty facilities and material-free recipes can have that counter, so evaluation checks shared recipe costs and actual dependencies. Development comparison preserves a same-plan observation separately from reoptimized results to avoid attributing staffing improvements to one skill.

Rescue mode shares the actual owned-roster input and excludes normal primaries, every binding replacement and backup reference from new staffing. The backend compiles blank ordinary working positions from effective normal slots; preview uses the complete result while saving preserves the sparse source. Recycling inherits by default. This retains existing rescue replacement behavior without implementing ordinary normal rotation or changing rescue mood thresholds. Unresolved backup conditions remain incomplete and cannot qualify an applicable candidate.

Scheduling Plan, Operator Mood and Dormitory Recovery retain their glossary meanings. The feature creates candidate configurations and evaluates existing behavior; no glossary change is needed.

## Alternatives considered

A skill-only generator cannot provide reproducible search, cancellation or reliable accounting. Exhaustive permutations of operators, replacements, groups and charging priorities are too large. Copying a fixed high-development example excludes smaller rosters and imports unsupported backup dependencies. Bounded construction from shared recommendations and reusable staffing structures accepts limited search coverage in exchange for inspectable results and reuse of the real evaluator.

## Consequences

Generation produces a single layout with no backups or layout switching. It uses actual owned progression, finite inventory and sanity valuation, with eight daily external gold units supplying stock rather than income. The default screen compares seven measured days after three warmup days. Search can miss better plans; the screening period does not prove indefinite sustainability or game execution. Daily supply is an average assumption rather than an account receipt calendar. Applying another layout requires the user to arrange actual facilities.

Optional development checks compare at most two owned operators. Costs remain separate from production stock and may be unknown when the progression cache differs. Hypothetical plans cannot be applied. Applying a verified current-progression plan replaces existing backups; an uncertain save response keeps autosaves paused until refresh, avoiding an overwrite from stale local state.

Rescue results use the separate rescue import endpoint after comparing both the normal source and previously saved rescue source. Generation and application do not change the normal plan or automatic-rescue switch. Inheritance compiles into one complete arrangement rather than restoring the former partial runtime scope. Rescue validation covers structure and inheritance, not recovery, exit or income simulation.

## Verification

The focused generator, rescue candidate, dialog, application, theme, income-session and plan-persistence suites pass 166 frontend cases across 14 files; ten backend income-validation cases pass. They cover ownership and unlocks, layout capacity, external supply, native validation before Workers, resource and mood rejection, request deadlines, cancellation, old results and explicit save boundaries. The retired prototype used dedicated frontend suites; their source is no longer part of the active implementation.

Thirty-six generated candidates across ordinary, broad and reference rosters pass native validation. An explicit 36-operator test roster starting with zero gold completes the actual three-day warmup and seven-day measured simulation: its 252 main plan has no material wait or unintended exhausted occupancy, with daily gold balance growth of 15.74286 including eight external units. Other trials confirm low-stock rejection and distinguish real exhaustion from an empty manufacturing facility. These are test rosters, not the user's account forecast.

With the same complete test roster, the Deep Sea standby plan produces 394.28506 sanity per day with multiple charging targets and 395.41003 with Gladiia only, a difference of 1.12497; the Smoke standby plan produces 363.26650. All three complete three warmup days and seven measured days without material waiting or unintended exhausted occupancy. The multiple-target Deep Sea plan has 927 consecutive charging gaps below one second, showing that continuous theoretical time cannot guarantee feasible game operations; evaluation preserves the shared score and discloses this limitation. The other two plans have no subsecond gaps, which still does not establish real-device validity.

The rescue compiler and route pass 115 focused cases, with 328 existing startup, takeover, handoff and rotation regression cases passing. Three actual rescue candidates each replace 27 ordinary work positions without overlap with any normal primary, replacement or backup reference, and recycling inherits 国度, 行铃 and their 旅骨 replacement. The original snapshot with seven normal backups returns incomplete; only the explicitly backup-free main-plan comparison returns complete validation for all three. Validation neither writes configuration nor synchronizes the roster.

Vite production build includes separate candidate and income Workers. A local browser check confirms the entry beside income calculation, eight gold / 4000 LMD equivalent default, cache-failure guidance and editor restoration after closing; the preview backend does not provide a full live generation flow. Structural governance checks pass separately, retaining only existing historical warnings. No live-device validation is claimed.
