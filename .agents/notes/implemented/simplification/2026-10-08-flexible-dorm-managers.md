---
title: Flexible dormitory managers
status: implemented
category: simplification
date: 2026-10-08
---

# Flexible dormitory managers

## Contract and simplification

[INV-SCHED-07] accepts dormitories with zero or one configured manager. Existing effective Free positions determine capacity; main-plan Free positions remain contiguous after named occupants and every dormitory retains at least one Free position. Named fixed replacements retain their existing capacity rules.

[INV-SCHED-02] selects the first operator with the recognized single-target recovery skill across all five positions of the final resolved roster, including replacements and idle fillers absent from the configured roster. Temporary recovery setup keeps that provider in its original slot and excludes it from target selection. Later providers follow ordinary resident rules and remain eligible recovery recipients. A roster without a single-target manager skips extra recovery setup; pending final-roster restoration still completes.

`Operators.init_and_validate` drops only the two-manager restriction. `refresh_dorm_manager_flags` covers all configured dormitory slots and replacements. `recovery_managers`, called by recovery planning and confirmation, queries the existing boolean skill cache for actual occupants and returns the first match. There is no numeric extraction, ranking, initialization rate preload, new configuration switch or additional cache. Resource reload invalidates skill results as before.


Skill matching accepts descriptions with or without the self-exclusion phrase, covering Indigo as well as ordinary single-target providers. Shared recovery descriptions such as Brewers remain outside single-target recognition.

## Verification and review

Offline tests cover zero through four configured managers, actual Free capacity and admission, backup transitions, preserved validation errors, single-target managers in slots three through five, newly encountered idle managers, replacement skills, first-position selection even when a later provider has a stronger skill, later-provider recovery and movement, cache reuse, resource reload and pending restoration. Existing group, rescue and recovery failure tests preserve their boundaries.

Standards review retains the existing skill cache, observed recovery confirmation and failure compensation. Specification review preserves named fixed beds and Free validation while removing the minimum manager count and first-two-slot recognition limit, with only the first recognized provider selected for recovery setup.
