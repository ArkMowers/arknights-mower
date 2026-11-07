---
title: Homebound T5 Workshop Scope
status: implemented
category: feature
date: 2026-10-09
---

# Homebound T5 Workshop Scope

[English](2026-10-09-traveler-t5-workshop.md) | [中文](2026-10-09-traveler-t5-workshop.zh.md)

## Contract

**[INV-WORKSHOP-02] T5 Specialist Priority**: Homebound recommendations and crafting allocation use only her elite-two T5 specialty, saved execution copies exclude non-T5 recipes, and higher-bonus workers retain execution priority.

Homebound (旅骨) supplies a 90 percent byproduct bonus for 手性屈光体 and 重相位对映体. Mower admits only the latter T5 recipe for this operator. Nian retains priority through her higher fixed bonus; Homebound remains an eligible fallback when selected. BOX ownership, elite-two unlock and Scheduling Plan exclusions retain their existing contracts.

## Implementation

Pre-flight review finds one production caller of `compile_workshop_data` in the resource generator. Recommendation and allocation share `operator_recipe_allowed`, and saved execution copies share `scope_workshop_items`. The change reuses these boundaries and removes no abstraction. The shared scoped-operator tuple replaces repeated exemption lists. No configuration schema, base scheduling mechanism or domain term changes; no glossary amendment is required.

The compiler accepts both 副产品 and 副产物, and emits separate exact-item rules for names joined by 或. Matching also accepts the combined item string from older generated metadata. Resource compilation preserves the official `char_4232_hbound` identity and elite-two level-one unlock. The operator policy requires the T5 recipe output 重相位对映体 even without BOX or specialty metadata. The operator scope excludes non-T5 recipes in recommendation, allocation and copied manual settings; saved settings remain unchanged. Existing specialist reservation and descending fixed-bonus ordering preserve Nian's priority.

Resource release `v2026.10.09-466ab33` lacks Homebound in its operator list and skill metadata. Current upstream game data provides her identity and tagged skill text. A selected external resource package remains authoritative; gameplay recognition requires a package containing Homebound's complete operator resources. Bundled recognition and skill data remain a coherent existing set. This change prepares resource compilation without installing or publishing a resource package.

## Verification

[Focused regressions](../../../../arknights_mower/tests/workshop_traveler_tests.py) cover tagged game text, both byproduct spellings, operator identity isolation for identical wording, older combined-item metadata, elite-two unlock, T5-only recommendations, allocation with and without Nian, unavailable BOX data and immutable manual settings.

The focused workshop suites pass 134 tests. On alpha baseline `a2348040`, governance regressions pass 25 tests and 21 subtests. Ruff and the repository structural gate pass; the gate retains two unrelated historical reference warnings.

The [growth-planning contract](../../../../docs/subsystems/growth-planning.md) owns the invariant.

## Standards Findings

PASS: Shared material policies preserve saved configuration and use existing resource-derived unlocks and fixed-bonus ordering.

## Spec Findings

PASS: Homebound supplies only 重相位对映体 in automatic recommendations and allocation; Nian retains priority when her higher-bonus recipe is selected.
