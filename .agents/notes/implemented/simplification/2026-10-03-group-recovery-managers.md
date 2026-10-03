---
title: Group Recovery Managers
status: implemented
category: simplification
date: 2026-10-03
---

# Group Recovery Managers

## Contract

[INV-SCHED-09] restores at most one configured dormitory group-recovery or shared-recovery manager per dormitory to spare intelligent-rescue capacity. Dormitory descriptions containing “所有干员的心情每小时恢复” qualify; Bingniang's distribution among unfinished residents also qualifies. Facility metadata must identify a dormitory. Single-target skills qualify only for a second pass when spare capacity remains and that dormitory has a restored group manager. Each dormitory restores at most one manager of each kind; self-recovery skills do not qualify.

Configured position does not establish skill eligibility. Recovery demand, unfinished residents, working assignments and specialized reservations still constrain restoration. Fiammetta retains her configured position. Final handoff restores the normal dormitory layout.

## Simplification Evidence

`_open_emergency_beds` is the sole consumer of the new group classifier. Both recovery classifiers reuse `_skill_index` and resource reload invalidation in `dorm_skills`; no duplicate file loader or per-operator state is introduced. The second restoration pass reuses the existing single-target classifier. Skill descriptions establish eligibility instead of a first-two-position assumption or hardcoded operator names. The existing single-target classifier and ordinary admission remain unchanged.

## Verification

Offline tests cover ordinary group recovery, shared recovery, single-target and self recovery, unrelated control-center descriptions, rich text, shared resource caches, reload invalidation, capacity shortage, one restored manager per kind and dormitory, group-before-single ordering, later configured positions, unfinished residents, working managers, reservations and Fiammetta.

## Review

Twelve focused offline suites pass 224 tests and four subtests, including one manager per kind and dormitory, group-before-single capacity and dual-kind skills. Scoped Ruff, formatting, whitespace checks and all three governance gates pass. An independent review of snapshot `87b68f6b622c76314081bac11ac97f9e78789fc2` passes both axes and independently verifies 220 tests and four subtests for skill eligibility and actual dispatch. A new independent review of final production snapshot `8caa0855d5e686dad4f6896bf7210c3af58067bb` passes both axes and independently verifies 224 tests and four subtests plus 12 additional boundary cases, including later configured positions, blocked candidates and actual bed-task dispatch projections. Three governance gates and scoped Ruff and formatting checks pass; all 3961 snapshot files retain their recorded hashes. These overlapping test sets are not added together. Glossary wording remains unchanged until exact bilingual approval.
