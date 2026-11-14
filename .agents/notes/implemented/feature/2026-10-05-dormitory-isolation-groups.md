---
title: Dormitory Isolation Groups
status: implemented
category: feature
date: 2026-10-05
---

# Dormitory Isolation Groups

## Contract

[INV-SCHED-23] defines best-effort separation before dormitory admission. Groups have no member-count limit; operators can belong to multiple groups. Isolation never raises recovery priority, takes a single-target bed for separation, defers otherwise valid admission or creates post-admission correction tasks. Unavoidable same-group cohabitation remains valid.

## Configuration and Admission

`Conf.dorm_isolation` stores independent lists of operator names and defaults to an empty list. Blank names, placeholders and duplicates within one group are rejected. Advanced settings provide group addition, deletion and the existing operator selector. Configuration autosave, plan export and advanced-settings import retain the groups; old configurations use the empty default.

Bed allocation compares the isolation score only after existing empty-bed and resident recovery ranking. A complete shift projection refines new secondary-bed arrivals after normal single-target allocation and submits the resulting roster once. Ordinary vacancy filling and intelligent rescue use the same admission score and pre-admission refinement. Unknown Free selection placeholders remain unresolved during projection and retain existing game selection rules; they never trigger later isolation correction. Existing residents remain in their positions when isolation settings change.

## Verification

`dorm_isolation_tests.py` validates preserved actual occupancy, deterministic projected refinement, unchanged single-target beds, accepted two-member cohabitation with a protected single-Free dormitory, unlimited and overlapping groups, full vacancy capacity and intelligent rescue. The complete shift regression verifies separation before submission and no later isolation movement. `configDormIsolation.test.js` checks nested autosave, group deletion, loading older configurations and advanced-settings export.

## Standards Findings

Pass. [INV-SCHED-23] is registered in the scheduling specification, coding standards and review checklist. Shared recovery ranking and bed ownership remain authoritative. Projections preserve actual occupancy; selection and correction retain their existing rules. The approved bilingual glossary wording is synchronized, and note, link and controlled-language gates pass.

## Spec Findings

Pass. Groups have no member-count limit, support overlapping membership and persist through advanced-settings import and export. Separation occurs before admission; occupied single-Free dormitories do not require takeover, unavoidable cohabitation remains valid and no post-admission isolation movement is generated. Unknown Free placeholders retain existing game selection semantics.
