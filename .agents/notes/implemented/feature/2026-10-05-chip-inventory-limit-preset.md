---
title: Chip Inventory Limit Preset
status: implemented
category: feature
date: 2026-10-05
---

# Chip Inventory Limit Preset

## Contract

The [weekly plan editor contract](../../../../docs/subsystems/weekly-plan-editor.md) defines [INV-UI-05]. The inventory limit toolbar provides one button for all eight chip stages. The question-mark help button immediately to its right states the small-chip limit of 5, chip-pack limit of 8, replacement of existing chip rules and execution only for selected stages.

## Simplification Review

The stage-options endpoint already supplies both chip drops for every chip stage. `createLimitRule` serves manual binding and preset generation; its optional limit retains the existing default of zero. No additional material mapping, persistence schema or scheduling branch is required.

## Implementation and Verification

`applyChipLimitPreset` constructs enabled AND rules from endpoint materials, replaces matching chip rules and retains other stage rules. The component writes the result to the current plan's existing configuration refs. Focused utility tests cover all eight bindings, both thresholds, repeated application, duplicate replacement, unchanged input and execution limited to selected stages.

## Standards Findings

Pass. Existing configuration ownership and inventory evaluation remain authoritative. The change uses existing domain terms and introduces no glossary changes.

## Spec Findings

Pass. One button binds small chips at 5 and chip packs at 8 to their respective stages; both drops must reach the limit before a stage is skipped. Existing all-stages-reached fallback remains in effect.
