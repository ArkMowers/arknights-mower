---
title: Rescue Facility Capacity and Dorm Batching
status: archived
category: bug-fix
date: 2026-10-04
---

> Superseded by [Configured Rescue Schedule](../../implemented/simplification/2026-10-04-configured-rescue-schedule.md).

# Rescue Facility Capacity and Dorm Batching

## Contract

[INV-SCHED-09] uses the full configured trade/manufacture slot count as facility level, including when replacing only part of a room. Levels one through three have trade limits 6/8/10 and manufacture capacity 24/36/54. Jaye's promoted combination uses the level-dependent trade limit; its conditional limit reduction is not a fixed capacity penalty. Unknown level or unmeasured unpromoted order accumulation contributes no assumed Jaye bonus. Dorothy counts active same-room Rhine Lab skills, including her own. Operator-added storage conversion excludes base warehouse capacity.

[INV-SCHED-03] defers ordinary recovery fillers while required primaries still await working replacements. Nonworking primaries remain eligible for shared-priority bed allocation. Same-cycle bed plans merge into pending rescue staffing without overwriting reserved slots; persistence matches the merged plan. A merged plan yields when its expanded operation budget conflicts with mandatory releases. Existing execution orders workplaces before dormitories.

## Simplification

The existing scoring function receives room level; no facility-level scanner is added. Existing staffing tasks own same-cycle bed arrangements; no extra dormitory task is created for those arrangements. The [scheduler contract](../../../../docs/subsystems/base-scheduler.md) owns these rules.

## Evidence

[Game building data](https://github.com/Kengxxiao/ArknightsGameData/blob/master/zh_CN/gamedata/excel/building_data.json) supplies phase capacities and slot counts. [Jaye's skills](https://prts.wiki/w/孑) distinguish order accumulation from the promoted combination. Bundled active skill descriptions supply Dorothy and storage conversion effects.

## Review

Standards Findings: No outstanding findings. Reuses existing selection, shared recovery tiers and task ownership. Merged arrangements preserve reservations and recheck mandatory-release budgets; no new device observation or persistent schema is introduced.

Spec Findings: No outstanding findings. Targeted offline suites pass 1213 tests and 20 subtests, covering one/two/three-slot trade capacity, partial replacements, the Rhine Lab pair, primary-before-filler admission, merged plans and insufficient operation windows.
