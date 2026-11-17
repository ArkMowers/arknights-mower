---
format: decision
title: RIIC AI planning
status: implemented
category: feature
date: 2026-10-13
---

# RIIC AI planning

## Problem

Mower AI has no tool for joining saved operator growth, the existing base combinations and facility assignments. Importing the external mechanics skill's full catalog duplicates Mower's maintained resources and its browser assets.

## Decision

The [AI assistant description](../../../../docs/subsystems/ai-assistant.md#riic-tools) defines three read-only tools: roster and combination context, current skill and nested-term queries, and detached staffing trials. Complete drafts use the same trial tool as primary-only assignments; the `plan_generation` topic guides single-layout design from current BOX and inventory. The [implementation](../../../../arknights_mower/agent/tools/riic.py) uses existing stage selection and BOX readers. User-declared ownership and growth remain transient and explicitly override BOX only in the current call.

The frontend and AI share twenty combination definitions in one JSON resource. Only the three absent v078 operators are supplemented; installed resource records take precedence. Supplemental character IDs resolve BOX ownership when the general operator map predates them. Existing glossary definitions retain their meaning; this adapter changes no scheduling execution or persisted schema.

## Alternatives considered

Copying the complete external catalogs and HTML browser preserves a second skill distribution but duplicates operator and term sources. A compact interpretation guide plus three absent records retains the required information with existing Mower readers.

A separate skill runner or optimizer adds a runtime dependency without improving the three required tool operations. The existing chat tool workflows dispatch the same functions. The user withdrew the separate generator button and fixed whole-plan constructor because maintaining predefined plans cannot cover different BOX states. The [archived prototype](../../archived/feature/2026-11-17-main-plan-generator.md) retains that comparison; existing skills and native validation own the replacement.

## Consequences

Trials expose ownership, growth, current skill stages, configured capacity and duplicate primary occupancy errors without saving or executing changes. Legacy primary assignments leave replacement matching unchecked. Complete drafts preserve replacement and additional group bindings and run native structural validation in isolated models. Rescue drafts resolve inherited slots and exclude normally reserved operators from new explicit staffing. Backup activation, actual mood and recovery, global interactions, power and long-term yield remain explicit limits. Successful checks do not establish executable long-term rotation or an optimal Scheduling Plan. Numeric validation still uses the existing frontend income dialog; this extension supplies no backend simulation runner.

The fixed external guide covers 432 operators. The shared catalog extends this checkout's 429 records with 德·托莱多, 克莱门莎 and 旅骨. Resource updates automatically supersede those supplements when they provide the same names.

## Verification

[Focused offline tests](../../../../arknights_mower/tests/riic_assistant_tests.py) cover current-slot upgrades, user overrides, missing BOX, ownership and growth errors, preserved-room conflicts, capacity and both model dispatch workflows. The [shared resource tests](../../../../arknights_mower/tests/building_skills_tests.py) cover supplemental BOX identity and installed-record precedence. Frontend tests cover the shared combinations and chat suggestion. Live model inference and device operation remain untested.

The external skill format check passes. GameData, Toolbox and PRTS checks report current; the Mower recycle source check times out, leaving aggregate freshness unknown. The pinned guide records that limitation separately from runtime resource coverage.

Mechanics queries also cover taxonomy, plan compatibility, supplemental operators, income export and source freshness. Numeric requests route to the [frontend income dialog](../../../../docs/subsystems/plan-editor.md#income-export), without claiming that AI tools ran the simulation. The [developer skill](../../../skills/mower-riic/SKILL.md) supplies shared-resource maintenance, fixed-source checks and focused verification entry points. Six additional query and schema tests pass, preserving unlocked skills, saved plans and sensitive-configuration isolation.

Complete-plan and execution tests also cover actual native group matching, ownership and growth of replacements and charging targets, rescue inheritance and reserved-name exclusions, safe context snapshots, and intact large JSON through the stored-chat tool path. These remain offline checks; no real model optimization or seven-day AI simulation is claimed.

A runnable draft is not an optimization result. The planning guide requires assessing relevant competitive cores from the actual BOX and explaining inclusion or exclusion through their mechanics and constraints. Identity-based support is separate from the supporter’s own skill unlocks. Comparable income simulations remain necessary before ranking candidates; neither structural validation nor saved Fiammetta targets establish the best arrangement.
