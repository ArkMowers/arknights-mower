---
title: Stable Dormitory Recovery Order
status: implemented
category: bug-fix
date: 2026-10-12
---

# Stable Dormitory Recovery Order

## Contract

[INV-SCHED-20] allocates movable recovering residents by recovery tier at admission, departure and recovery-configuration events. The complete configured high/low position order determines allocation, including ordinary options before high-priority options. Without explicit ordinary options, single-target positions precede ordinary positions in configured room order. Equal-speed positions preserve incumbents where their tiers fit. Mood deficits rank unassigned candidates within a tier and do not relocate compatible incumbents. Mood changes alone produce no arrangement.

Reservations, excluded residents, mandatory personal-limit departures and fixed replacement positions retain protection. Full-mood ordinary residents remain available as fillers without taking recovery precedence. Actual room arrangements invalidate affected recovery deadlines, confirm changed single-target ownership, observe the final roster and rebuild derived return tasks.

## Implementation

The shared `prioritize_new_dorm_recovery` entry replaces separate arrival-preemption and vacancy loops with one allocation over projected beds. Retaining compatible incumbents before assigning remaining candidates limits relocation and makes repeated allocation stable. Admission, ordinary fill and merged release reuse the same entry. Pre-flight inspection finds no need for another planner, persisted cooldown or recovery-rate prediction; configured order remains the speed preference.

Backup preservation checks accept invalidated projected deadlines while still verifying residents and bed positions. Migration planning does not write projected beds or deadlines into actual recovery caches. Clearing an already empty position preserves room timing. Empty ordinary positions do not claim incumbent retention, and displaced full-mood fillers use remaining positions in complete configured order after unfinished residents are assigned.

## Verification

Offline regressions cover Ling entering an ordinary bed behind lower-tier residents, cross-tier target correction, equal-tier retention, default room order, independent ordinary-position order and ordinary options before targets, batched clearances, protected beds, unchanged live observations and repeated allocation. Recovery tests cover single-target confirmation and fresh room timing after ordinary and target changes.

Review regressions exercise cached and projected backup transitions that relocate working covers and replace a dormitory manager together. Affected deadlines become unknown only in the projection, unchanged-room deadlines remain valid, and actual recovery caches remain intact. Pending same-room returns wait for final-roster observations; independent-room returns retain their timing. Device-seam simulations provide final-roster deadlines before checking resumed return and trade-order planning.

## Standards Findings

Pass: isolated projections preserve actual occupancy and measured mood; complete configured high/low ordering reuses alpha configuration without another schema. Explicit backup positions, fixed replacements and reservations retain protection. Ruff and repository structural governance pass. The bilingual glossary is synchronized with explicit user approval.

## Spec Findings

Pass: 2185 focused offline scheduler tests and 24 Vue configuration tests pass on alpha b8ef9d98. A further 495 focused recovery, group and backup tests pass after threading pending group transitions through whole-room timing refresh. Coverage includes 81 tier combinations, independent ordinary order, ordinary options before targets, batched release, equal-tier stability, single-target confirmation and fresh stationary-roommate deadlines. An additional 55 group-confirmation tests and 193 priority/isolation/convergence tests pass after the final timing-context and isolation guards. No live-device verification is performed.

After the review and CI repairs, 80 focused scheduling suites pass 3491 tests and 14 additional projection-caller suites pass 806 tests. These include the previously failing backup, return-planning and capacity scenarios, manager replacement during work relocation, no-op vacancies, independent-room timing and final-roster readback before return planning. Ruff, format, governance and diff checks pass; the runs retain 14 existing warnings in total.
