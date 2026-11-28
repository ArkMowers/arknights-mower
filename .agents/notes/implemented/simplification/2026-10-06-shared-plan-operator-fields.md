---
title: Shared Plan Operator Fields
status: implemented
category: simplification
date: 2026-10-06
---

# Shared Plan Operator Fields

## Contract

[INV-SCHED-26] preserves additive legacy backup lists and isolated source settings while extending them with removals.

## Simplification

The plan store uses OPERATOR_CONF_FIELDS for addition conversion, removal conversion, operator replacement and operator collection. This removes the duplicated eleven-field collection from backup_conf_convert_list. Dormitory order remains a separate non-operator field. The same eleven keys cover all editor operator lists, including 宿舍保留干员.

PlanConfig.merge_config remains the single merge implementation; Operators.merge_plan is its sole production caller. The shared selector renders both main and backup controls without duplicating selection or drag behavior. Empty strings are absent from merged operator lists.

## Verification

Focused store tests cover all keys through load, save, import and export. Existing standby, mood-limit and operator-edit tests cover adjacent fields.
