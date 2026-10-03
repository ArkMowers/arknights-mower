---
title: Group Recovery Managers
status: implemented
category: simplification
date: 2026-10-03
---

# Group Recovery Managers

## Contract

[INV-SCHED-09] restores only configured dormitory group-recovery or shared-recovery managers to spare intelligent-rescue capacity. Dormitory descriptions containing “所有干员的心情每小时恢复” qualify; Bingniang's distribution among unfinished residents also qualifies. Facility metadata must identify a dormitory. Single-target and self-recovery skills do not qualify.

Configured position does not establish skill eligibility. Recovery demand, unfinished residents, working assignments and specialized reservations still constrain restoration. Fiammetta retains her configured position. Final handoff restores the normal dormitory layout.

## Simplification Evidence

`_open_emergency_beds` is the sole consumer of the new group classifier. Both recovery classifiers reuse `_skill_index` and resource reload invalidation in `dorm_skills`; no duplicate file loader or per-operator state is introduced. Skill descriptions establish eligibility instead of a first-two-position assumption or hardcoded operator names. The existing single-target classifier and ordinary admission remain unchanged.

## Verification

Offline tests cover ordinary group recovery, shared recovery, single-target and self recovery, unrelated control-center descriptions, rich text, shared resource caches, reload invalidation, capacity shortage, later configured positions, unfinished residents, working managers, reservations and Fiammetta.

## Review

Twelve focused offline suites pass 217 tests and four subtests. Scoped Ruff, formatting, whitespace checks and all three governance gates pass. Standards Findings and Spec Findings require independent snapshot review before push. Glossary wording remains unchanged until exact bilingual approval.
