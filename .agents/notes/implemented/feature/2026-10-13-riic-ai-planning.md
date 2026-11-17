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

The [AI assistant description](../../../../docs/subsystems/ai-assistant.md#riic-tools) defines three read-only tools: roster and combination context, current skill and nested-term queries, and detached staffing trials. Existing-plan changes use the same validation tool as primary-only assignments; `plan_review` guides repairs, local improvements and base-skill development advice for owned operators. The assistant does not create plans from scratch or change layouts to increase income. The `mower_tutorial` topic reads fixed sections from the current installed guide, with source and missing coverage explicit. The [implementation](../../../../arknights_mower/agent/tools/riic.py) uses existing stage selection and BOX readers. User-declared actual ownership and growth remain transient and explicitly override BOX only in the current call. Development targets remain hypothetical and never replace those facts.

The frontend and AI share twenty combination definitions in one JSON resource. Only the three absent v078 operators are supplemented; installed resource records take precedence. Supplemental character IDs resolve BOX ownership when the general operator map predates them. Existing glossary definitions retain their meaning; this adapter changes no scheduling execution or persisted schema.

## Alternatives considered

Copying the complete external catalogs and HTML browser preserves a second skill distribution but duplicates operator and term sources. A compact interpretation guide plus three absent records retains the required information with existing Mower readers.

A separate skill runner or optimizer adds a runtime dependency without improving the three required tool operations. The existing chat tool workflows dispatch the same functions. The user withdrew the separate generator button and fixed whole-plan constructor because maintaining predefined plans cannot cover different BOX states. The [archived prototype](../../archived/feature/2026-11-17-main-plan-generator.md) retains that comparison. The later single-layout drafting guidance also gave the assistant responsibility for choosing a whole arrangement; the user narrowed this feature to correcting and locally improving an existing plan. Full-plan validation remains necessary to preserve its bindings and check proposed changes.

## Consequences

Trials expose ownership, growth, current skill stages, configured capacity and duplicate primary occupancy errors without saving or executing changes. Legacy primary assignments clear modified-room bindings and leave replacement matching unchecked, so local edits use full-plan copies. Complete drafts preserve replacement and additional group bindings and run native structural validation in isolated models. Rescue drafts resolve inherited slots and exclude normally reserved operators from new explicit staffing. Backup activation, actual mood and recovery, global interactions, power and long-term yield remain explicit limits. Successful checks do not establish executable long-term rotation or an optimal Scheduling Plan. Numeric validation still uses the existing frontend income dialog; this extension supplies no backend simulation runner.

The fixed external guide covers 432 operators. The shared catalog extends this checkout's 429 records with 德·托莱多, 克莱门莎 and 旅骨. Resource updates automatically supersede those supplements when they provide the same names.

The successful income record can be handed to the assistant as a review draft, preserving its original input and result rather than reading the current editor. Four bounded attachments report source, parameters, original plan, work/rest and exhausted occupancy, deferrals and limited events, with omissions explicit. Existing drafts and busy conversations are protected; the user sends the staged message through the existing attachment and chat boundaries. This adds no route or model-triggering action. Historical source fields remain unknown when absent.


The review also distinguishes configuration, simulation-model and scheduler implementation failures. Suspected code defects route through the fixed local `code_diagnosis` index and actual source snippets, preserving scanned locations, hashes, missing states and the difference between current and historical versions. The assistant investigates suspected implementation defects without requiring plan changes to hide them. Simulation-only evidence first produces a reproduction and feedback draft; relative hours cannot become incident dates or log reference IDs. Real device events use the existing inspection and evidence-window path. Sending still requires explicit user agreement and the existing interface's actual time and valid references; the assistant does not repair code automatically.

## Verification

[Focused offline tests](../../../../arknights_mower/tests/riic_assistant_tests.py) cover current-slot upgrades, user overrides, missing BOX, ownership and growth errors, preserved-room conflicts, capacity and both model dispatch workflows. The [shared resource tests](../../../../arknights_mower/tests/building_skills_tests.py) cover supplemental BOX identity and installed-record precedence. Frontend tests cover the shared combinations and chat suggestion. Live model inference and device operation remain untested.

The external skill format check passes. GameData, Toolbox and PRTS checks report current; the Mower recycle source check times out, leaving aggregate freshness unknown. The pinned guide records that limitation separately from runtime resource coverage.

Mechanics queries also cover taxonomy, plan compatibility, supplemental operators, income export and source freshness. Numeric requests route to the [frontend income dialog](../../../../docs/subsystems/plan-editor.md#income-export), without claiming that AI tools ran the simulation. The [developer skill](../../../skills/mower-riic/SKILL.md) supplies shared-resource maintenance, fixed-source checks and focused verification entry points. Six additional query and schema tests pass, preserving unlocked skills, saved plans and sensitive-configuration isolation.

Complete-plan and execution tests also cover actual native group matching, ownership and growth of replacements and charging targets, rescue inheritance and reserved-name exclusions, safe context snapshots, and intact large JSON through the stored-chat tool path. These remain offline checks; no real model optimization or seven-day AI simulation is claimed.

Structural validation is not evidence of an improvement. The guide requires comparable original-plan and candidate simulations before reporting income gains or rankings, distinguishes identity-based support from the supporter's own skill unlocks, and traces exhausted occupancy through configuration and recorded events. A work/rest ratio or absent deferral resolution alone does not establish a scheduling defect or an end-of-run deadlock.

The updated [prompt checks](../../../../arknights_mower/tests/ai_prompt_contract_tests.py) pass eleven tests and nineteen subtests, verifying that existing-plan scope, tutorial routing, hypothetical growth and evidence requirements reach the actual prompt and registered knowledge tool. Tutorial and review-handoff behavior use the focused checks named in the [maintenance guide](../../../skills/mower-riic/references/maintenance.md#定向验证). The text and source checks remain separate from behavior results; no live model inference, device operation or measured income improvement is claimed.

Four focused review, income-diagnosis and code-diagnosis prompt tests pass, including eight subtests. They verify source-index routing and the separation of simulation material, source versions, real incident times and sendable feedback evidence; they do not validate a particular suspected defect.
