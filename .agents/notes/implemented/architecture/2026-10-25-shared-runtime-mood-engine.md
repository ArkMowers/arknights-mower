---
format: decision
title: Share the income engine's mood calculations with native scheduling
status: implemented
category: architecture
date: 2026-10-25
---

# Share the income engine's mood calculations with native scheduling

## Problem

Native scheduling previously used room observations and empirical depletion rates, while the [income-image decision](../../implemented/feature/2026-10-14-plan-income-export.md) runs a fixed TypeScript calculator in a browser Worker. Scheduling from calculated mood needs that calculator's skill effects while retaining native task execution, observations and restart recovery. Copying its formulas into Python would create two implementations to maintain. The [Arknights Mower Base Infrastructure & Scheduling Subsystem Specification](../../../../docs/subsystems/base-scheduler.md#calculated-mood-test) owns the resulting operational rules.

## Decision

The default-off advanced Scheduling Plan setting “实时心情计算调控” selects calculated mood for the [existing ordinary rotation rules](../../../../docs/subsystems/base-scheduler.md#predictive-mood-control). This decision owns the shared formulas and runtime boundary. [`runtimeMood.ts`](../../../../ui/src/riic/runtimeMood.ts) adapts observed input to the income engine's existing mood and dormitory-recovery functions. The build bundles those functions and their dependencies into plain JavaScript shipped with the Python application, executed by embedded `quickjs-ng`. User installations need neither Node.js nor an open web page. Income calculation retains its browser Worker; both paths share formula source and skill-threshold behavior while keeping their state and clocks independent.

Python's [`CalculatedMood`](../../../../arknights_mower/utils/calculated_mood.py) owns observations, elapsed time, operation events and persisted model data. JavaScript evaluates skill effects and rates from supplied input. Future queries and Projected Occupancy use detached state; computed values do not replace actual room measurements. Runtime snapshots store plain model data and omit operator references to the new runtime class, so older versions can still deserialize observed occupants and pending tasks. Startup restores compatible model data and then performs fresh initial observations, preserving started work. Observation and operation-event ownership prevents counting a confirmed mood change again after its readback. Native execution keeps training policy, physical arrangements and compensation with their existing owners.

Cached Skland elite phase and level select unlocked skills when available; the user explicitly selected full-growth skills for operators without a valid growth cache. Dormitory atmosphere uses the maximum for the configured level. The setting help discloses both assumptions. These inputs do not write assumed growth or ownership into BOX. Facility levels follow the running plan's startup snapshot, while changed growth caches refresh skill inputs. Existing unquantified-skill reports remain visible in native logs.

Depletion Rate, Initial Mood Observation, Valid Mood Cache and Actual and Projected Occupancy retain their existing meanings. This choice adds calculation and observation behavior without renaming those concepts or changing their definitions; no glossary edit is needed.

## Alternatives considered

A Python translation removes the embedded JavaScript dependency but duplicates skill formulas and makes income and runtime fixes diverge. Requiring Node.js at runtime adds a separate user installation and process lifecycle. Depending on a browser Worker makes ordinary scheduling require an active page. A bundled JavaScript artifact with an embedded runtime keeps the formula source shared and fits Python's existing ownership of scheduler state, at the cost of an additional packaged runtime and a reproducible build step.

## Verification

The final 29 focused Python selections pass in five independent processes: 59 core, 279 legacy-behavior, 240 consumer, 313 scheduling and 28 configuration checks, totaling 919. The [core runtime tests](../../../../arknights_mower/tests/calculated_mood_tests.py) exercise real QuickJS calculations, exact-zero skill boundaries, isolated future queries and projections, fresh initialization despite recent caches, card completion, both training slots, growth-cache updates and startup facility levels. Production confirmation checks reject stale unstarted recovery and departure intents before a physical tap, retain started or explicit arrangements, and prevent submission when saving fails. The real crafting caller confirms three successful batches with Mudrock's full-growth fixed cost, settles six mood points once, then accepts an observed 22 as calibration; unreadable readback stays unknown and a failed pre-submit save causes no submission.

The [startup tests](../../../../arknights_mower/tests/calculated_mood_startup_tests.py) exercise actual restoration with legacy, compatible and invalidated models, and SQLite serialization readable without the new calculation class. [Consumer](../../../../arknights_mower/tests/mood_calculation_consumers_tests.py) and [projection-consumer](../../../../arknights_mower/tests/mood_calculation_projection_consumers_tests.py) tests cover replacement readiness, recovery deadlines, recall, native rotation and unchanged-failure retention without polling. Package verification runs resources collected by the real packaging helper after CRLF conversion with an empty executable search path. The frontend's 65 focused checks and production build pass. Bundle/source verification and document structural checks pass separately from behavior evidence. Review confirms the recorded responsibility boundaries; real-device behavior and complete platform release builds remain unobserved.

## Consequences

Sharing formula source avoids maintaining a Python copy, but adds a packaged JavaScript runtime and a build artifact that must be regenerated when its sources change. Hash and source checks detect stale or damaged artifacts; they do not establish game accuracy. Missing growth caches intentionally use full-growth skills, atmosphere assumes 1,000 points per configured level, and some skills remain unquantified. Unknown facility inputs or uncertain operations retain unknown mood until normal observations calibrate them, rather than creating extra patrols. Users can keep the default disabled mode when these assumptions are unsuitable. Native and income scheduling policies remain separate, so shared skill formulas do not make simulated income proof of real-device feasibility.
