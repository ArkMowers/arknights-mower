---
title: Native Intelligent Rescue
status: implemented
category: simplification
date: 2026-10-02
---

# Native Intelligent Rescue

## Contract

[INV-SCHED-09] retains native rescue entry and measured recovery targets. Optional intelligent rescue uses Mower for temporary staffing without external assistance. Candidates require a current readable card mood at least their normal shift-off threshold plus one. Trade order agents never receive ordinary temporary working assignments; eligible trade order runs continue and restore the observed temporary roster.

Each facility reads actual products. Automatic mastery and building skills share the existing Skland synchronization endpoint, BOX file and cached character reader. The same snapshot supplies ownership, elite phase and level; a file change invalidates both readers without a separate identity marker. Unlocked versions follow skill-group replacement rules; unavailable growth uses active card icons. Manufacturing and trade facilities compare combinations using supported local skill effects; power, office, reception and control use their facility scores. Unknown or cross-facility effects contribute no assumed benefit. Selection shares candidate reservations and a used-name set across rooms. Dormitory and training staffing retain their specialized boundaries. Missing eligible workers leave explicit vacancies.

The episode freezes ordinary shifts and backup transitions, persists unfinished staffing and handoff, and reconciles actual rooms after restart. Mood checks replace only missing or newly ineligible temporary workers and continue ordinary collection. Full primary recovery, dormitory priorities, Fiammetta, crafting, training and measured exit retain their existing contracts.


Selection compares supported effects within bounded candidate pools: 48 manufacturing/trade candidates and 16 others. It approximates efficiency and does not claim an optimum over every skill or operator.

## Simplification

Existing selection, resource reload, run-order compensation, dormitory planning and history data remain shared. The building-skill page consumes the same unlocked versions, marks unowned, locked and replaced entries, and filters by facility, ownership, skill state and text. Missing data adds no operator or skill status label.

## Review

Standards Findings: candidate pools and image recognition are bounded; confirmed growth or active icons prevent assuming elite unlocks. No external device owner or duplicate recovery pipeline remains.

Spec Findings: temporary workers exclude all trade order agents, low or unreadable card moods, all episode recovery primaries and specialized reservations. Production remains frozen between required temporary repairs; trade order runs preserve their normal eligibility and restore temporary staffing.


Verification: 581 related offline Python tests pass; final automatic-rescue regressions pass 49 tests. Four frontend suites pass 34 tests and the production build passes. Governance and automatic-rescue checks pass 63 tests and 4 subtests; all three governance gates, scoped Ruff, Prettier and whitespace checks pass. No live-device integration runs are performed.

The shared-reader regression verifies one file parse for mastery and building-skill queries, then a shared refresh after synchronization changes the file. Existing synced mastery data requires no new download.

Ordinary room-recovery fixtures specify no active task, so an unconfigured mock cannot acquire the specialized staffing failure path. Retry budgets, immediate user-stop propagation and production checks remain intact; room recovery, intelligent rescue and scheduler regressions pass 175 tests and 20 subtests.
