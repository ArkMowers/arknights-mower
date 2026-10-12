---
title: Same-Group Primary Replacements
status: implemented
category: simplification
date: 2026-10-12
---

# Same-Group Primary Replacements

## Contract

[INV-SCHED-22] accepts configured replacements between distinct primaries in the same nonempty group regardless of facility type. Both operators retain their primary identities. Empty groups, cross-group replacements and self-replacements remain invalid. Secondary bindings use the selected group and its replacement list. Complete matching determines dynamic bed demand: required recovering primaries assigned as replacements consume no additional dynamic bed. Working targets retain their assigned primaries at work; fixed dormitory targets supply their own recovery positions. Unassigned required recovering primaries need available dynamic beds. Each assigned name counts once. Ordinary idle replacements, reservations, mood checks and training protection retain their existing rules.

## Simplification

`Operators.is_same_group_primary_replacement` removes the dormitory prerequisite from the shared predicate. Validation, shift planning, exhausted support and correction already consume that predicate; all callers use its facility-independent name. Validation counts the required-member set minus the names in the complete assignment. Runtime excludes the same assigned names before dynamic bed allocation, including same-room working exchanges; no temporary recovery reservation is created for a working cover. Fixed dormitory recovery still requires an actual dormitory position, so accepting working primaries adds no fixed beds or Free capacity. No configuration field, wrapper or alternative matching implementation is introduced.

The existing [dormitory replacement decision](2026-10-05-same-group-dorm-replacements.md) retains its recovery contract; this decision amends its facility restriction. The existing secondary-binding membership rule remains binding.

## Verification

Offline tests cover one-way and reciprocal working-primary configuration within one room and across rooms, primary identity, absence of grouped dormitories and fixed recovery capacity, and invalid group or self relationships. A working-primary exchange exercises complete matching, dynamic-bed reservation release and projected occupancy without changing live positions. Existing dormitory and multiple-binding regressions cover the shared callers. The focused scheduling suites pass 691 tests; Ruff passes. Bed regressions cover a one-bed mixed group, required-cover preference over idle covers, true static shortages, unavailable runtime beds and a fully reserved bed with a pure working exchange. The existing Pydantic fixture emits one serialization warning.

## Standards Findings

PASS: Shared matching and projection boundaries remain unchanged. The user explicitly approves the exact bilingual glossary wording before it is written. Governance structural checks pass against the alpha comparison base.

## Spec Findings

PASS: Same-group primary replacement validation no longer requires a dormitory primary. All remaining relationship and runtime eligibility checks remain binding.
