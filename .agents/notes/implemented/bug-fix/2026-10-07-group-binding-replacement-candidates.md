---
title: Group Binding Replacement Candidates
status: implemented
category: bug-fix
date: 2026-10-07
---

# Group Binding Replacement Candidates

The one-click replacement source menu and existing-target warning include replacements from every main and backup Scheduling Plan column. Operators configured only in `group_bindings[].replacement` remain selectable. Collection preserves plan data and deduplicates names; replacement preserves group labels and unrelated operators.

[INV-UI-10]

## Verification

Focused tests exercise main-only and backup-only additional-column replacements, Chinese pinyin filtering, names shared across columns, unchanged collection inputs and replacement of the selected source across its bindings. Legacy single-column and configuration-list tests retain their coverage.

## Simplification Audit

Both production consumers call `collect_plan_operators`. The existing Set supplies deduplication, and the existing replacement function traverses additional bindings. The collection uses the same binding traversal without introducing an interface or changing persisted data.

## Standards Findings

Pass. [INV-UI-10] is registered in the editor specification, coding standards and review checklist. Collection remains free of mutations, and governance checks pass.

## Spec Findings

Pass. Main-only and backup-only additional-column reproductions become selectable. The existing replacement function updates every matching binding while preserving other entries. The focused frontend suites pass all 48 tests.
