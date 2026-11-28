---
title: Backup Operator List Removal
status: implemented
category: feature
date: 2026-10-06
---

# Backup Operator List Removal

## Contract

[INV-SCHED-26] applies each active backup's operator additions followed by per-field removals in backup order. Deactivation rebuilds effective lists from the main Scheduling Plan and remaining active backups without mutating source lists. Legacy backups without removals retain additive behavior.

## Simplification

One removal map extends the existing PlanConfig merge boundary. The existing operator-field collection also drives frontend removal conversion and operator replacement; no separate scheduling path is introduced. PlanConfig.merge_config has one production caller, Operators.merge_plan, which serves runtime switching and validation.

## Interface

BackupPlanConf.removed_operators stores comma-separated operator names keyed by the existing operator-list field names. The editor labels normal backup selections 增 and 减; rescue plans retain their existing single-list controls. 宿舍保留干员 renders directly below the dormitory blacklist on the normal plan page, outside advanced settings. Removal wins over addition within one backup; later backups can add removed operators again. Unsupported keys fail schema validation. Refresh-trading removal matches the operator name before any room qualifier.

## Verification

Focused offline tests cover all operator-list fields, source isolation, activation order, deactivation, legacy plans, schema rejection, serialization and frontend editing.

## Standards Findings

PASS: additions and removals share the existing isolated merge boundary. Unsupported removal keys fail schema validation; source lists remain unchanged. The editor reuses SlickOperatorSelect and the operator-field collection, retains editing locks, labels columns 增 and 减, and leaves selection placeholders blank. Existing 36px selection height and 12px form spacing remain unchanged; backup columns stay side by side at every viewport width. The advanced-settings action bar retains 12px bottom spacing independently of the shared centering rule. Ruff, frontend ESLint and whitespace checks pass. The approved glossary wording is synchronized in both languages.

## Spec Findings

PASS: 106 focused backend tests with 4 subtests and 49 focused frontend tests cover removal, full-list clearing, active backup order, deactivation, legacy behavior, source isolation, runtime construction, autosave, transfer, operator replacement and rescue-store isolation. Browser verification of the actual Plan component confirms separate controls, overlap cancellation, unchanged main lists and the relocated 宿舍保留干员 field outside advanced settings. The explanatory alert is absent. The frontend build updates local static assets; existing dependency and chunk-size warnings remain.
