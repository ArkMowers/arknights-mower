---
title: Operator growth planning
status: implemented
category: feature
date: 2026-10-07
---

# Operator growth planning

Growth planning shares the existing mastery database and material budget. Promotion and module choices use a small persistent goal file; actual training keeps its readiness checks. The subsystem contract owns material, statistics and farming semantics.

Pre-flight simplification removes the duplicated recommendation decomposition and the unused whole-queue readiness calculator. One remaining-cost calculation serves skill targets, modules, promotion and workshop requests. Existing workshop allocation and MAA weekly-plan persistence remain authoritative.

[INV-GROWTH-01] prevents double spending and premature training. Focused offline tests cover prerequisite deduplication, partial mastery targets, paid stages, chip conversion, statistics, manual backup restoration and MAA binding.

The interface exposes mutually exclusive elite-two level-one, module-threshold and maximum-level goals. Skill and module selections retain the minimum required prerequisite, and module targets include all remaining stages through the selected level, defaulting to maximum. Direct level, basic-skill, mastery and module costs stay separate; crafting fees appear separately and enter the aggregate LMD budget once.

Plan creation records persistent intent and can attempt automatic dispatch; its `added` acknowledgement alone does not prove a task is queued. The explicit start endpoint instead validates the selected target and acknowledges an observed DB-keyed queue task. Missing finished materials, disabled automation, stopped scheduling and occupied training return their actual blocking reasons. Focused tests verify selected targets, idempotence and truthful queue acknowledgements.

Observed growth valuation uses a pinned Yituliu snapshot, reports unpriced or incomplete costs, and excludes inventory and unfinished goals. Opened modules expose consumed module data blocks; completed basic skills and mastery expose volume-three skill-summary equivalents. The [subsystem contract](../../../../docs/subsystems/growth-planning.md) owns the formulas, coverage limits and persistence rules.

The sanity card also displays direct LMD and EXP investment and natural-regeneration days at 240 sanity per day; unknown historical crafting fees are excluded.
