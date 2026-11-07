---
title: Crafting Idle Rest Priority
status: implemented
category: feature
date: 2026-10-06
---

# Crafting Idle Rest Priority

## Contract

[INV-SCHED-07] keeps staffing identity above internal rest order. When both mastery and automatic crafting are active, ordinary idle operators use interleaved non-T5, T5 and skill-summary lists, preserving each name's first occurrence. Only positions occupied by eligible crafting candidates are permuted; unlisted operators retain their original ranking positions. This occurs before applying bed limits, so an eligible first-choice crafter can replace a later-choice crafter inside the admission range. Other identity tiers, fixed dormitory positions, exclusions and reservations keep their existing behavior.

## Simplification and Implementation

`resting_key` and takeover costs remain unchanged. The shared `crafting_rest_order` permutes crafting entries after normal candidate sorting in ordinary filling, rescue filling and single-target allocation. Selection preserves the chosen crafter even when other cards have the same mood. No configuration field, persistent cache, additional task or parallel dormitory policy is introduced. Reading the current lists makes edits and deactivation immediately effective. Complete residents remain subject to existing admission eligibility and no same-tier takeover is added.

## Verification

Focused offline tests cover interleaving, duplicates, unequal list lengths, deactivation, live edits, other identity tiers, training support, exclusions and shared candidate sorting. Existing bed takeover, admission and rescue suites cover scheduling boundaries. Card-estimated candidates and the post-merge fill task preserve the same order. Validation passes 363 tests and 4 subtests, Ruff and repository governance.

## Standards Findings

The shared priority function and existing invariant cover the change. Exact bilingual glossary wording is approved by the user. Tests perform no device operations.

## Spec Findings

Crafting candidates only exchange their own ranking positions, without collective priority over other idle operators. Training support retains replacement priority; fixed dormitory managers receive no additional bed.
