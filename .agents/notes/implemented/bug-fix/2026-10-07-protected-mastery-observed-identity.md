---
title: Protected Mastery Observed Identity
status: implemented
category: bug-fix
date: 2026-10-07
---

# Protected Mastery Observed Identity

## Contract

[INV-SCHED-29] admits protected continuation only for the same trainee and skill uniquely resolved from the current waiting-collect panel. The same room observation retains that identity after collection for immediate continuation. A protected empty room without that observation waits, including after cache clearing or restart. Historical mastery tiers and cached plan identity do not identify the previous trained skill.

## Implementation

The skill-page reader determines protection with a boolean result. Its single production caller does not need a skill identity field or a full three-skill scan after finding partial mastery. Removing that field preserves the existing bounded read and eliminates inference from historical tiers. The strict panel resolver supplies identity at collection and the start boundary. Existing glossary definitions remain accurate.

## Verification

Offline tests cover restart with unique and multiple historical partial-mastery skills, unreadable tiers, stale panel rejection, different trainees and skills, immediate continuation after collection, and rejection before plan or staffing changes. Existing mastery and material-selection tests cover the surrounding dispatch and protection contracts.
